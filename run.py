# -*- coding: utf-8 -*-
"""Homework 1.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1kPw4c06loi1JL2IKL97B2W3TAVzNYmkL
"""
import numpy as np
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.model_selection import train_test_split
import pandas as pd
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("train_file", type=str, help="Path to the training data")
parser.add_argument("test_file", type=str, help="Path to the test data")
parser.add_argument("output_file", type=str, help="Path to save the output predictions")
args = parser.parse_args()
train_filepath = args.train_file
test_filepath = args.test_file
output_filepath = args.output_file

train_data = pd.read_csv(train_filepath)
train_data.head()

test_data = pd.read_csv(test_filepath)
test_data.head()

# Preprocessing the utterances with TF-IDF for both train and test sets
vectorizer = TfidfVectorizer(max_features=5000)
X_train = vectorizer.fit_transform(train_data['UTTERANCES']).toarray()
X_test = vectorizer.transform(test_data['UTTERANCES']).toarray()
print(X_train, X_test)

# Fill NaN values with an empty string
train_data['CORE RELATIONS'].fillna('', inplace=True)

# Preprocessing the relations (multi-label binarization)
mlb = MultiLabelBinarizer()
y_train = mlb.fit_transform(train_data['CORE RELATIONS'].apply(lambda x: x.split()))
print(y_train)

# Split training data into training and validation sets
X_train_split, X_val, y_train_split, y_val = train_test_split(X_train, y_train, test_size=0.2, random_state=42)

# Convert the data to PyTorch tensors
X_train_split = torch.tensor(X_train_split, dtype=torch.float32)
X_val = torch.tensor(X_val, dtype=torch.float32)
X_test = torch.tensor(X_test, dtype=torch.float32)
y_train_split = torch.tensor(y_train_split, dtype=torch.float32)
y_val = torch.tensor(y_val, dtype=torch.float32)

# Define the MLP model using PyTorch
class MLP(nn.Module):
    def __init__(self, input_size, hidden_size1, hidden_size2, output_size):
        super(MLP, self).__init__()
        self.fc1 = nn.Linear(input_size, hidden_size1) #first hidden layer
        self.fc2 = nn.Linear(hidden_size1, hidden_size2) # second hidden layer
        self.fc3 = nn.Linear(hidden_size2, output_size) # output layer
        self.relu = nn.ReLU() # activation function
        self.sigmoid = nn.Sigmoid()
        self.dropout = nn.Dropout(p=0.3) # always have low dropiout
        self.batchnorm1 = nn.BatchNorm1d(hidden_size1) # batch normalization for 1st hidden layer
        self.batchnorm2 = nn.BatchNorm1d(hidden_size2) # batch normalization for 2nd hidden layer

    def forward(self, x):
        x = self.fc1(x)
        x = self.relu(x)
        x = self.batchnorm1(x)
        x = self.dropout(x)
        x = self.fc2(x)
        x = self.relu(x)
        x = self.batchnorm2(x)
        x = self.dropout(x)
        x = self.fc3(x)
        x = self.sigmoid(x)  # Apply sigmoid activation in the output layer
        return x

# Model parameters
input_size = X_train_split.shape[1]
hidden_size1 = 512
hidden_size2 = 512
output_size = y_train_split.shape[1]

# Initialize the model
model = MLP(input_size, hidden_size1, hidden_size2, output_size)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)

# Focal Loss implementation
'''class FocalLoss(nn.Module):
    def __init__(self, alpha=1, gamma=2):
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, inputs, targets):
        BCE_loss = nn.BCELoss(reduction='none')(inputs, targets)
        pt = torch.exp(-BCE_loss)
        F_loss = self.alpha * (1-pt)**self.gamma * BCE_loss
        return torch.mean(F_loss)'''

# loss function
criterion = nn.BCELoss()   # Binary cross-entropy loss for multi-label classification

# optimizer
optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-5)

# Learning rate scheduler
scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'min', patience=5, factor=0.5)

# Training the model
num_epochs = 100
batch_size = 32

# Lists to store training and validation losses and accuracies
train_losses = []
val_losses = []
train_accuracies = []
val_accuracies = []

# Custom data loader for batching
def get_batches(X, y, batch_size):
    for i in range(0, X.size(0), batch_size):
        yield X[i:i + batch_size], y[i:i + batch_size]

for epoch in range(num_epochs):
    model.train()
    total_loss = 0
    total_correct = 0  # For accuracy calculation
    total_samples = 0  # Total samples processed

    for X_batch, y_batch in get_batches(X_train_split, y_train_split, batch_size):
        # Forward pass
        outputs = model(X_batch)
        loss = criterion(outputs, y_batch)

        # Backward pass and optimization
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item()

        # Calculate accuracy for the batch
        predicted = (outputs > 0.3).float()  # Convert probabilities to binary
        total_correct += (predicted == y_batch).sum().item()
        total_samples += y_batch.size(0) * y_batch.size(1)  # Total samples in the batch

    # Calculate training loss and accuracy
    train_loss = total_loss / (X_train_split.size(0) / batch_size)
    train_accuracy = total_correct / total_samples
    train_losses.append(train_loss)
    train_accuracies.append(train_accuracy)

    # Validation at the end of each epoch
    model.eval()
    total_val_loss = 0
    total_val_correct = 0
    total_val_samples = 0

    with torch.no_grad():
        val_outputs = model(X_val)
        val_loss = criterion(val_outputs, y_val).item()

        # Calculate validation accuracy
        val_predicted = (val_outputs > 0.3).float()
        total_val_correct += (val_predicted == y_val).sum().item()
        total_val_samples += y_val.size(0) * y_val.size(1)

    val_accuracy = total_val_correct / total_val_samples
    val_losses.append(val_loss)
    val_accuracies.append(val_accuracy)

    # scheduler.step(val_loss)  # Adjust learning rate

    # print(f'Epoch [{epoch+1}/{num_epochs}], '
         # f'Train Loss: {train_loss:.4f}, Train Accuracy: {train_accuracy:.4f}, '
         # f'Validation Loss: {val_loss:.4f}, Validation Accuracy: {val_accuracy:.4f}')

# Final prediction on the test set
model.eval()
with torch.no_grad():
    y_test_pred = model(X_test)

# Convert predicted probabilities to binary
y_test_pred_binary = (y_test_pred > 0.3).float()

# Convert binary predictions back to relation labels
predicted_relations = mlb.inverse_transform(y_test_pred_binary.numpy())

# Output the predicted relations for the test set
test_data['Core Relations'] = [' '.join(rel) for rel in predicted_relations]
print(test_data[['UTTERANCES', 'Core Relations']])
test_data[['ID', 'Core Relations']].to_csv(output_filepath, index=False)

# Plotting the training and validation loss
plt.figure(figsize=(12, 5))

# Loss plot
plt.subplot(1, 2, 1)
plt.plot(range(1, num_epochs + 1), train_losses, label='Train Loss')
plt.plot(range(1, num_epochs + 1), val_losses, label='Validation Loss')
plt.title('Loss over Epochs')
plt.xlabel('Epochs')
plt.ylabel('Loss')
plt.legend()

# Accuracy plot
plt.subplot(1, 2, 2)
plt.plot(range(1, num_epochs + 1), train_accuracies, label='Train Accuracy')
plt.plot(range(1, num_epochs + 1), val_accuracies, label='Validation Accuracy')
plt.title('Accuracy over Epochs')
plt.xlabel('Epochs')
plt.ylabel('Accuracy')
plt.legend()

plt.tight_layout()
plt.show()

# Load the CSV file
df = pd.read_csv(output_filepath)

# Check if the 'core relations' column exists
if 'Core Relations' in df.columns:
    # Get the frequency of unique labels in 'core relations' column
    label_counts = df['Core Relations'].value_counts()

    # Print the frequency of each unique label
    print("Frequency of Unique Labels in 'Core Relations' Column:")
    print(label_counts)
else:
    print("'core relations' column not found in the CSV file.")

empty_rows = df.isnull().sum(axis=1).sum()
print("Number of empty rows:", empty_rows)

from sklearn.metrics import multilabel_confusion_matrix
import seaborn as sns

# Step 1: Convert the validation outputs to binary predictions
val_predicted = (val_outputs > 0.5).float()

# Step 2: Convert PyTorch tensors to NumPy arrays
y_val_np = y_val.numpy()
val_predicted_np = val_predicted.numpy()

# Step 3: Compute the confusion matrix for each label
conf_matrices = multilabel_confusion_matrix(y_val_np, val_predicted_np)

# Step 4: Display confusion matrix for each label using heatmap
"""for i, conf_matrix in enumerate(conf_matrices):
    plt.figure(figsize=(6, 4))
    sns.heatmap(conf_matrix, annot=True, fmt='d', cmap='Blues', cbar=False,
                xticklabels=['Pred 0', 'Pred 1'],
                yticklabels=['True 0', 'True 1'])
    plt.title(f'Confusion Matrix for Label {i+1}')
    plt.ylabel('Actual')
    plt.xlabel('Predicted')
    plt.show() """