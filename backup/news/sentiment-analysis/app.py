from flask import Flask, request, json
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from pymongo import MongoClient
import datetime
from collections import defaultdict


app = Flask(__name__)
tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")



@app.route("/transform")
def transform_data():

    client = MongoClient('mongodb://localhost:27017') #connect to extraction db
    db = client.test_db
    collection = db.test
    #load data from yesterday
    yesterday = ((datetime.datetime.today()) - datetime.timedelta(days=1)).strftime('%m-%d-%Y')
    query = {
        'date': {'$eq': yesterday}
    }
    data = collection.find(query, {'_id':0})
    data_to_transform = []
    #initialize new collection in extraction db for transformed data
    db = client.test_db
    collection = db.transformedData
    for t in data:
        """
        There are two kinds of data: 1. Stock Market, 2. Company Specifics
        For stock market data, we take as is. 
        For company specific:
        1. For ones coming in from yfinance, we take as is
        2. For both nyt and mediastack, we will only pick the docs where theres a match between search_term and entities.
            That is because, a lot of what is queried from these two sources may not contain what we are looking for.
        """
        if t['source'] == 'yfinance':
            data_to_transform.append(t)
        else:
            if t['search_term'] in t['entities'] and t['search_term'] != "Stock Market":
                data_to_transform.append(t)
            elif t['search_term'] == "Stock Market":
                data_to_transform.append(t)
    try:
        collection.insert_many( list(data_to_transform) )
        return {
            'message': 'Successfully pushed transformed data to mongo'
        }
    except:
        return {
            'message': 'Error pushing transformed data.'
        }

@app.route("/sentiment")
def hello_world():
    client = MongoClient('mongodb://localhost:27017') #connect to extraction db
    db = client.test_db
    collection = db.transformedData
    yesterday = ((datetime.datetime.today()) - datetime.timedelta(days=1)).strftime('%m-%d-%Y')
    query = {
        'date': {'$eq': yesterday}
    }
    test = collection.find(query)
    transformed_data = []
    for t in test:
        transformed_data.append(t)
    
    data  = defaultdict(dict)
    for i in range(len(transformed_data)):
        if transformed_data[i]['date'] not in data:
            data[ transformed_data[i]['date'] ] = {}
        if transformed_data[i]['search_term'] not in data[ transformed_data[i]['date'] ]:
            data[ transformed_data[i]['date'] ][ transformed_data[i]['search_term'] ] = {
                'avg_sentiment': [],
                'news': []
            }

        inputs = tokenizer(transformed_data[i]['news'], padding = True, truncation = True, return_tensors='pt')
        outputs = model(**inputs)
        predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)

        positive = predictions[:, 0].tolist()
        negative = predictions[:, 1].tolist()
        neutral = predictions[:, 2].tolist()
        sentiment_data = {'Headline':transformed_data[i]['news'],
            'sentiment': {
                'positive': positive[0],
                'negative': negative[0],
                'neutral': neutral[0] 
            },
            'source': transformed_data[i]['source']
        }
        data[ transformed_data[i]['date'] ][ transformed_data[i]['search_term'] ]['news'].append(sentiment_data)

    #connect and send data to sentiment store db
    client2 = MongoClient('mongodb://localhost:27018') #connect to extraction db
    db2 = client2.test_db
    collection2 = db2.test
    try:
        collection2.update_one(
            {'date': yesterday},
            {'$set': {'data': data}},
            upsert=True
        )
        return {"message":"Data push to sentiment DB- Succeded"}
    except:
        return {"message":"Data push to sentiment DB failed"}



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8002,debug=True)


"""
inputs = tokenizer(data_to_test, padding = True, truncation = True, return_tensors='pt')
outputs = model(**inputs)
predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)

positive = predictions[:, 0].tolist()
negative = predictions[:, 1].tolist()
neutral = predictions[:, 2].tolist()
#df = pd.DataFrame(table, columns = ["Headline", "Positive", "Negative", "Neutral"])
#response = df.to_json(orient='records')[1:-1].replace('},{', '} {')
"""