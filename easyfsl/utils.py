"""
General utilities
"""

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torchvision
from matplotlib import pyplot as plt
from torch import Tensor, nn
from torch.utils.data import DataLoader
from tqdm import tqdm

from easyfsl.methods import FewShotClassifier

from sklearn.metrics import f1_score
from sklearn import metrics
import random

def plot_images(images: Tensor, title: str, images_per_row: int):
    """
    Plot images in a grid.
    Args:
        images: 4D mini-batch Tensor of shape (B x C x H x W)
        title: title of the figure to plot
        images_per_row: number of images in each row of the grid
    """
    plt.figure()
    plt.title(title)
    plt.imshow(
        torchvision.utils.make_grid(images, nrow=images_per_row).permute(1, 2, 0)
    )


def sliding_average(value_list: List[float], window: int) -> float:
    """
    Computes the average of the latest instances in a list
    Args:
        value_list: input list of floats (can't be empty)
        window: number of instances to take into account. If value is 0 or greater than
            the length of value_list, all instances will be taken into account.

    Returns:
        average of the last window instances in value_list

    Raises:
        ValueError: if the input list is empty
    """
    if len(value_list) == 0:
        raise ValueError("Cannot perform sliding average on an empty list.")
    return np.asarray(value_list[-window:]).mean()


def predict_embeddings(
    dataloader: DataLoader,
    model: nn.Module,
    device: Optional[str] = None,
) -> pd.DataFrame:
    """
    Predict embeddings for a dataloader.
    Args:
        dataloader: dataloader to predict embeddings for. Must deliver tuples (images, class_names)
        model: model to use for prediction
        device: device to cast the images to. If none, no casting is performed. Must be the same as
            the device the model is on.
    Returns:
        dataframe with columns embedding and class_name
    """
    all_embeddings = []
    all_class_names = []
    with torch.no_grad():
        for images, class_names in tqdm(
            dataloader, unit="batch", desc="Predicting embeddings"
        ):
            if device is not None:
                images = images.to(device)
            all_embeddings.append(model(images).detach().cpu())
            if isinstance(class_names, torch.Tensor):
                all_class_names += class_names.tolist()
            else:
                all_class_names += class_names

    concatenated_embeddings = torch.cat(all_embeddings)

    return pd.DataFrame(
        {"embedding": list(concatenated_embeddings), "class_name": all_class_names}
    )


def evaluate_on_one_task(
    model: FewShotClassifier,
    support_images: Tensor,
    support_labels: Tensor,
    query_images: Tensor,
    query_labels: Tensor,
) -> Tuple[int, int]:
    """
    Returns the number of correct predictions of query labels, and the total number of
    predictions.
    """
    model.process_support_set(support_images, support_labels)
    predictions = model(query_images).detach().data
    number_of_correct_predictions = int(
        (torch.max(predictions, 1)[1] == query_labels).sum().item()
    )

    predicted_labels = torch.max(predictions, 1)[1]

    return number_of_correct_predictions, len(query_labels), predicted_labels, query_labels


def evaluate(
    model: FewShotClassifier,
    data_loader: DataLoader,
    device: str = "cuda",
    use_tqdm: bool = True,
    tqdm_prefix: Optional[str] = None,
) -> float:
    """
    Evaluate the model on few-shot classification tasks
    Args:
        model: a few-shot classifier
        data_loader: loads data in the shape of few-shot classification tasks*
        device: where to cast data tensors.
            Must be the same as the device hosting the model's parameters.
        use_tqdm: whether to display the evaluation's progress bar
        tqdm_prefix: prefix of the tqdm bar
    Returns:
        average classification accuracy
    """
    # We'll count everything and compute the ratio at the end
    total_predictions = 0
    correct_predictions = 0

    # eval mode affects the behaviour of some layers (such as batch normalization or dropout)
    # no_grad() tells torch not to keep in memory the whole computational graph
    model.eval()
    predictions_all = []
    query_labels_all = []

    with torch.no_grad():
        # We use a tqdm context to show a progress bar in the logs
        with tqdm(
            enumerate(data_loader),
            total=len(data_loader),
            disable=not use_tqdm,
            desc=tqdm_prefix,
        ) as tqdm_eval:
            for _, (
                support_images,
                support_labels,
                query_images,
                query_labels,
                _,
            ) in tqdm_eval:

                # Check support_images, support_labels etc individual length chatgpt
                print("LENGTH I support_images: " + str(len(support_images)))
                print("LENGTH I support_labels: " + str(len(support_labels)))
                print("LENGTH I query_images: " + str(len(query_images)))
                print("LENGTH I query_labels: " + str(len(query_labels)))
                
                
                
                # # Combine the two lists into a list of tuples, where each tuple contains corresponding elements from both lists
                # combined_task_lists = list(zip(support_images, support_labels, query_images, query_labels))

                # # Shuffle the combined list
                # random.shuffle(combined_task_lists)

                # # Unzip the shuffled list to get back the randomized lists
                # support_images, support_labels, query_images, query_labels = zip(*combined_task_lists)

                # # Convert the tuples back to tensors
                # support_images = torch.stack(support_images)
                # support_labels = torch.stack(support_labels)
                # query_images = torch.stack(query_images)
                # query_labels = torch.stack(query_labels)

                correct, total, predictions_per_task, query_labels_per_task = evaluate_on_one_task(
                    model,
                    support_images.to(device),
                    support_labels.to(device),
                    query_images.to(device),
                    query_labels.to(device),
                )

                total_predictions += total
                correct_predictions += correct

                predictions_all.extend(predictions_per_task.detach().cpu().numpy())
                query_labels_all.extend(query_labels_per_task.cpu().numpy())
                # print(query_labels_per_task)
                # Log accuracy in real time
                tqdm_eval.set_postfix(accuracy=correct_predictions / total_predictions)


    query_labels_all = np.array(query_labels_all)
    predictions_all = np.array(predictions_all)


    print("Number of Query Labels - Val: " + str(len(query_labels_all)))
    print("Number of Predicted Labels - Val: " + str(len(predictions_all)))

    f1 = f1_score(query_labels_all, predictions_all, average=None)
    print("F1 Score is: " + str(f1))

    mse = mean_squared_error(query_labels_all, predictions_all)
    mae = mean_absolute_error(query_labels_all, predictions_all)

    print("Mean Squared Error (MSE): " + str(mse))
    print("Mean Absolute Error (MAE): " + str(mae))  


    return correct_predictions / total_predictions


def compute_average_features_from_images(
    dataloader: DataLoader,
    model: nn.Module,
    device: Optional[str] = None,
):
    """
    Compute the average features vector from all images in a DataLoader.
    Assumes the images are always first element of the batch.
    Returns:
        Tensor: shape (1, feature_dimension)
    """
    all_embeddings = torch.stack(
        predict_embeddings(dataloader, model, device)["embedding"].to_list()
    )
    average_features = all_embeddings.mean(dim=0)
    if device is not None:
        average_features = average_features.to(device)
    return average_features

def mean_squared_error(y_true, y_pred):
    return np.mean((y_true - y_pred)**2)

def mean_absolute_error(y_true, y_pred):
    return np.mean(np.abs(y_true - y_pred))

