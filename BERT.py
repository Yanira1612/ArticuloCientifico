# -*- coding: utf-8 -*-
"""BERT.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1O5fWfjkYJIxelwdM5poYHyzLRVovNVSR
"""

pip install transformers

from transformers import BertModel, BertTokenizer, AdamW, get_linear_schedule_with_warmup
import torch
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, f1_score
from torch import nn, optim
from torch.utils.data import Dataset, DataLoader
import pandas as pd
from textwrap import wrap

# Inicialización
RANDOM_SEED = 42
MAX_LEN = 200
BATCH_SIZE = 16
DATASET_PATH = '/content/drive/MyDrive/Train_data.csv'
test_csv_file_path = '/content/drive/MyDrive/Test_data.csv'
NCLASSES = 3

np.random.seed(RANDOM_SEED)
torch.manual_seed(RANDOM_SEED)
device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
print(device)

# Cargar dataset
from google.colab import drive
drive.mount('/content/drive')

df = pd.read_csv(DATASET_PATH)
df = df[0:10000]

df_prueba = pd.read_csv(test_csv_file_path)
df_prueba = df_prueba[0:10000]

print(df.head())
print(df.shape)
print("\n".join(wrap(df['review'][0])))

# Reajustar dataset
## df['label'] = df['sentiment'].map({'Positivo': 1, 'Neutro': 0, 'Negativo': -1})
df['label'] = df['sentiment'].map({'Positivo': 2, 'Neutro': 1, 'Negativo': 0})
df.drop('sentiment', axis=1, inplace=True)
df.head()

#df_prueba['label'] = df_prueba['sentiment'].map({'Positivo': 2, 'Neutro': 1, 'Negativo': 0})
#df_prueba.drop('sentiment', axis=1, inplace=True)
df_prueba.head()

# TOKENIZACIÓN
PRE_TRAINED_MODEL_NAME = 'bert-base-multilingual-cased'
tokenizer = BertTokenizer.from_pretrained(PRE_TRAINED_MODEL_NAME)

# Ejemplo tokenización
sample_txt = 'Yo realmente amo esta película'
tokens = tokenizer.tokenize(sample_txt)
token_ids = tokenizer.convert_tokens_to_ids(tokens)
print('Frase: ', sample_txt)
print('Tokens: ', tokens)
print('Tokens numéricos: ', token_ids)

# Codificación para introducir a BERT
encoding = tokenizer.encode_plus(
    sample_txt,
    max_length = 160, #longitud máxima
    truncation = True,
    add_special_tokens = True,
    return_token_type_ids = False,
    padding='max_length',
    return_attention_mask = True,
    return_tensors = 'pt'
)

encoding.keys()

print(tokenizer.convert_ids_to_tokens(encoding['input_ids'][0]))
print(encoding['input_ids'][0])
print(encoding['attention_mask'][0])

# CREACIÓN DATASET

class DatosDataset(Dataset):

  def __init__(self,reviews,labels,tokenizer,max_len):
    self.reviews = reviews
    self.labels = labels
    self.tokenizer = tokenizer
    self.max_len = max_len

  def __len__(self):
      return len(self.reviews)

  def __getitem__(self, item):
    review = str(self.reviews[item])
    label = self.labels[item]
    encoding = tokenizer.encode_plus(
        review,
        max_length = self.max_len,
        truncation = True,
        add_special_tokens = True,
        return_token_type_ids = False,
        padding='max_length',
        return_attention_mask = True,
        return_tensors = 'pt'
        )


    return {
          'review': review,
          'input_ids': encoding['input_ids'].flatten(),
          'attention_mask': encoding['attention_mask'].flatten(),
          'label': torch.tensor(label, dtype=torch.long)
      }

# Data loader:

def data_loader(df, tokenizer, max_len, batch_size):
  dataset = DatosDataset(
      reviews = df.review.to_numpy(),
      labels = df.label.to_numpy(),
      tokenizer = tokenizer,
      max_len = MAX_LEN
  )

  return DataLoader(dataset, batch_size = BATCH_SIZE, num_workers = 2)

df_train, df_test = train_test_split(df, test_size = 0.2, random_state=RANDOM_SEED)

train_data_loader = data_loader(df_train, tokenizer, MAX_LEN, BATCH_SIZE)
test_data_loader = data_loader(df_test, tokenizer, MAX_LEN, BATCH_SIZE)

# EL MODELO

class BERTSentimentClassifier(nn.Module):

  def __init__(self, n_classes):
    super(BERTSentimentClassifier, self).__init__()
    self.bert = BertModel.from_pretrained(PRE_TRAINED_MODEL_NAME)
    self.drop = nn.Dropout(p=0.3) #evita overfiting
    self.out = nn.Linear(self.bert.config.hidden_size, n_classes) #Añade capa lineal

  def forward(self, input_ids, attention_mask):
    bert_output = self.bert(
        input_ids = input_ids,
        attention_mask = attention_mask
    )
    pooled_output = bert_output.pooler_output ##
    output = self.drop(pooled_output)
    return self.out(output)

model = BERTSentimentClassifier(NCLASSES)
model = model.to(device) #Llevarlo a la GPU

print(model)

# ENTRENAMIENTO
EPOCHS = 10
optimizer = AdamW(model.parameters(), lr=2e-5, correct_bias=False)
total_steps = len(train_data_loader) * EPOCHS
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps = 0,
    num_training_steps = total_steps
)

loss_fn = nn.CrossEntropyLoss().to(device)

# Iteración entrenamiento
def train_epoch(model, data_loader, loss_fn, optimizer, device, scheduler, n_examples):
  model = model.train()
  losses = []
  correct_predictions = 0

  for batch in data_loader:
    input_ids = batch['input_ids'].to(device)
    attention_mask = batch['attention_mask'].to(device)
    labels = batch['label'].to(device)

    outputs = model(input_ids=input_ids, attention_mask=attention_mask)
    _, preds = torch.max(outputs, dim=1)
    loss = loss_fn(outputs, labels)
    correct_predictions += torch.sum(preds == labels)
    losses.append(loss.item())

    loss.backward()

    nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
    optimizer.step()
    scheduler.step()
    optimizer.zero_grad()

  return correct_predictions.double()/n_examples, np.mean(losses)

def eval_model(model, data_loader, loss_fn, device, n_examples):
  model = model.eval()
  losses = []
  correct_predictions = 0
  with torch.no_grad():
    for batch in data_loader:
      input_ids = batch['input_ids'].to(device)
      attention_mask = batch['attention_mask'].to(device)
      labels = batch['label'].to(device)
      outputs = model(input_ids = input_ids, attention_mask = attention_mask)
      _, preds = torch.max(outputs, dim=1)
      loss = loss_fn(outputs, labels)
      correct_predictions += torch.sum(preds == labels)
      losses.append(loss.item())

  return correct_predictions.double()/n_examples, np.mean(losses)

# Entrenamiento

for epoch in range(EPOCHS):
  print('Epoch {} de {}'.format(epoch+1, EPOCHS))
  print('------------------')
  train_acc, train_loss = train_epoch(model, train_data_loader, loss_fn, optimizer, device, scheduler, len(df_train))
  test_acc, test_loss = eval_model(model, test_data_loader, loss_fn, device, len(df_test))
  print('Entrenamiento: Loss: {}, accuracy: {}'.format(train_loss, train_acc))
  print('Validación: Loss: {}, accuracy: {}'.format(test_loss, test_acc))
  print('')

def classifySentiment(review_text):
  encoding_review = tokenizer.encode_plus(
      review_text,
      max_length = MAX_LEN,
      truncation = True,
      add_special_tokens = True,
      return_token_type_ids = False,
      pad_to_max_length = True,
      return_attention_mask = True,
      return_tensors = 'pt'
      )

  input_ids = encoding_review['input_ids'].to(device)
  attention_mask = encoding_review['attention_mask'].to(device)
  output = model(input_ids, attention_mask)
  _, prediction = torch.max(output, dim=1)
  print("\n".join(wrap(review_text)))
  if prediction == 0:
    return 'Negativo'
  elif prediction == 1:
    return 'Neutro'
  elif prediction == 2:
    return 'Positivo'

review_text = "No estoy ni en contra ni a favor del congreso"

print(classifySentiment(review_text))

# Predicciones en el conjunto de prueba
test_predictions = [classifySentiment(test_document) for test_document in df_prueba['review']]

true_labels = df_prueba['sentiment'].tolist()

# Calcular métricas
precision = precision_score(true_labels, test_predictions, average='weighted')
recall = recall_score(true_labels, test_predictions, average='weighted')
f1 = f1_score(true_labels, test_predictions, average='weighted')

# Imprimir métricas redondeadas a 2 decimales
print(f'Precision: {round(precision, 2)}')
print(f'Recall: {round(recall, 2)}')
print(f'F1 Score: {round(f1, 2)}')