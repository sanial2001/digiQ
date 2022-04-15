import random
import os
from flask import Flask, render_template, request, jsonify
from azure.cosmos import CosmosClient, PartitionKey
from flask_cors import CORS, cross_origin

# DB 
def manage_db():
    endpoint = os.environ['DB_ENDPOINT']
    key = os.environ['DB_KEY']
    database_name = os.environ['DB_NAME']
    container_queues_name = os.environ['DB_CONT_Q']
    container_users_name = os.environ['DB_CONT_U']
    
    client = CosmosClient(endpoint, key)
    database = client.create_database_if_not_exists(id=database_name)
    container_queues = database.create_container_if_not_exists(
        id=container_queues_name, 
        partition_key=PartitionKey(path="/id")
    )
    container_users = database.create_container_if_not_exists(
        id=container_users_name, 
        partition_key=PartitionKey(path="/id")
    )
    return container_queues, container_users

container_queues, container_users = manage_db()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.route("/")
def hello():
    return render_template("home.html")


queue_id_available = [True]*10000

# get all queues
@app.route('/api/getallqueues', methods=["GET"])
def get_all_queue():
    query = f"SELECT c.id, c.name, c.city, c.is_active, c.count, c.time_per_user_m, c.total_time, c.admin, c.tag, c.users FROM c WHERE c.is_active = true"
    allqueues = list(container_queues.query_items(query=query, enable_cross_partition_query=True))

    return jsonify(allqueues), 200

# get all queues city
@app.route('/api/getallqueuescity', methods=["POST"])
def get_all_queue_city():
    input_json = request.get_json(force=True) 
    city = str(input_json['city']).lower()
    city = city[0].upper()+city[1:]
    query = f"SELECT c.id, c.name, c.city, c.is_active, c.count, c.time_per_user_m, c.total_time, c.admin, c.users, c.tag FROM c where c.city = '{city}' AND c.is_active = true"
    allqueues = list(container_queues.query_items(query=query, enable_cross_partition_query=True))

    return jsonify(allqueues), 200


# get all users
@app.route('/api/getallusers', methods=["GET"])
def get_all_users():
    query = "SELECT c.id, c.phone, c.ncreatedqueues, c.nactivequeues, c.activequeues, c.createdqueues FROM c"
    allusers = list(container_users.query_items(query=query, enable_cross_partition_query=True))

    return jsonify(allusers), 200

# signup
@app.route('/api/signup', methods=['POST'])
@cross_origin(supports_credentials=True)
def signup():
    input_json = request.get_json(force=True) 

    username, password, phone = input_json['username'], input_json['password'], input_json['phone']

    newUser = {
        'id':str(username), 
        'password':password, 
        'phone':phone, 
        'activequeues':[], 
        'nactivequeues': 0, 
        'createdqueues':[], 
        'ncreatedqueues':0
    }

    try:
        item_response = container_users.read_item(item=username, partition_key=username)
        if item_response['id'] == username:
            dictToReturn = {"message":"User with this username already exists. Choose a different user id"}
            return jsonify(dictToReturn), 403
    except:
        container_users.create_item(body=newUser) 
  
    dictToReturn = {"message": "success"}
    return jsonify(dictToReturn), 201


# login
@app.route('/api/login', methods=['POST'])
@cross_origin(supports_credentials=True)
def login():
    input_json = request.get_json(force=True) 

    username, password = str(input_json['username']), input_json['password']

    try:
        item_response = container_users.read_item(item=username, partition_key=username)
    except:
        return jsonify({"message":"The username you entered doesnot exist"}), 404
    
    
    if password != item_response['password']:
        return jsonify({"message":"Your username and password don't match"}), 401


    dictToReturn = {"message": "success"}
    return jsonify(dictToReturn), 201


# create queue
@app.route('/api/createqueue', methods=['POST'])
def createqueue():
    input_json = request.get_json(force=True) 

    username, name, time_per_user_m, city, tag = str(input_json['username']), input_json['name'], int(input_json['time']), str(input_json['city']).lower(), input_json['tag']
    city = city[0].upper()+city[1:]

    queueId = random.randint(1000, 9999)
    while True:
        if queue_id_available[queueId] == True:
            break
        random.randint(1000, 9999)

    queue_id_available[queueId] = False

    queueId = str(queueId)
    
    newQueue = {
        'id':str(queueId), 
        'name':name, 
        'is_active':True, 
        'count':0, 
        'users':[], 
        'time_per_user_m':time_per_user_m, 
        'total_time':0,
        'admin':username,
        'city':city,
        'tag':tag
    }

    try:
        userupdate = container_users.read_item(item=username, partition_key=username)
        userupdate['createdqueues'].append(newQueue)
        userupdate['ncreatedqueues'] += 1
        container_users.replace_item(username, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)

    except:
        return jsonify({"message":"Unauthorized"}), 403

    container_queues.create_item(body=newQueue) 
    dictToReturn = {"message":"Your queue was created successfully", "queueId":queueId}
    return jsonify(dictToReturn), 201

# delete queue
@app.route('/api/deletequeue', methods=['POST'])
def deletequeue():
    input_json = request.get_json(force=True) 

    queueId, username = str(input_json['queueId']), str(input_json['username'])
 
    try:
        queueupdate = container_queues.read_item(item=queueId, partition_key=queueId)
        
        if queueupdate['admin'] != username:
            return jsonify({"messsage":"Unauthorized"}), 403
    
        inqueueusers = queueupdate['users']
        for user in inqueueusers:
            userupdate = container_users.read_item(item=user, partition_key=user)

            userupdate['nactivequeues'] -= 1
            for q in range(len(userupdate['activequeues'])):
                if userupdate['activequeues'][q]['id'] == queueId:
                    del userupdate['activequeues'][q]
                    break          

            # userupdate['activequeues'].remove(queueId)
            container_users.replace_item(user, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
            

        
        userupdate = container_users.read_item(item=username, partition_key=username)

        for q in range(len(userupdate['createdqueues'])):
            if userupdate['createdqueues'][q]['id'] == queueId:
                del userupdate['createdqueues'][q]
                break

        userupdate['ncreatedqueues'] -= 1
        
        container_users.replace_item(username, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
        
        container_queues.delete_item(str(queueId), str(queueId), populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
        queue_id_available[int(queueId)] = True
        dictToReturn = {"message":"Your queue was deleted successfully"}
        return jsonify(dictToReturn), 201


    except Exception as e:
        print(e)
        return jsonify({"message":"The queue doesn't exist"}), 404


# deactivate queue
@app.route('/api/deactivatequeue', methods=['POST'])
def deactivatequeue():
    input_json = request.get_json(force=True) 
    queueId = str(input_json['queueId'])

    try:
        queueupdate = container_queues.read_item(item=queueId, partition_key=queueId)
        queueupdate['is_active'] = False
        queueupdate['count'] = 0
        inqueueusers = queueupdate['users'] 
        queueupdate['users'] = []
        queueupdate['total_time'] = 0

        for user in inqueueusers:
            userupdate = container_users.read_item(item=user, partition_key=user)

            userupdate['nactivequeues'] -= 1
            for q in range(len(userupdate['activequeues'])):
                if userupdate['activequeues'][q]['id'] == queueId:
                    del userupdate['activequeues'][q]
                    break          

            container_users.replace_item(user, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
            
        admin = queueupdate['admin']
        userupdate = container_users.read_item(item=admin, partition_key=admin)
        for q in range(len(userupdate['createdqueues'])):
            if userupdate['createdqueues'][q]['id'] == queueId:
                userupdate['createdqueues'][q]['is_active'] = False
                userupdate['createdqueues'][q]['count'] = 0
                print("wh")
                userupdate['createdqueues'][q]['users'] = []
                userupdate['createdqueues'][q]['total_time'] = 0
                break
        
        container_users.replace_item(admin, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
        


        container_queues.replace_item(queueId, queueupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
        dictToReturn = {"message":"Your queue was deactivated successfully"}
        return jsonify(dictToReturn), 201

    except Exception as e:
        print(e)
        return jsonify({"message":"The queue doesn't exist"}), 404
        

# activate queue
@app.route('/api/activatequeue', methods=['POST'])
def activatequeue():
    input_json = request.get_json(force=True) 
    queueId = str(input_json['queueId'])

    try:
        queueupdate = container_queues.read_item(item=queueId, partition_key=queueId)
        
        admin = queueupdate['admin']
        userupdate = container_users.read_item(item=admin, partition_key=admin)
        for q in range(len(userupdate['createdqueues'])):
            if userupdate['createdqueues'][q]['id'] == queueId:
                userupdate['createdqueues'][q]['is_active'] = True
                break
        
        container_users.replace_item(admin, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
        
        
        
        queueupdate['is_active'] = True
        container_queues.replace_item(queueId, queueupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
        dictToReturn = {"message":"Your queue was activated successfully"}
        return jsonify(dictToReturn), 201
    
    except:
        return jsonify({"message":"The queue doesn't exist"}), 404

# get user info
@app.route('/api/getuserinfo', methods=["POST"])
def get_user_info():
    input_json = request.get_json(force=True) 

    username = str(input_json['username'])

    try:
        userdetails = container_users.read_item(item=username, partition_key=username)
        userdetails['activequeues'].sort(key=lambda x: x['time'])
    except:
        return jsonify({"message":"No user with the username found"}), 404

    return jsonify(userdetails), 200

# join queue
@app.route('/api/joinqueue', methods=['POST'])
def joinqueue():
    input_json = request.get_json(force=True) 
    queueId, username = str(input_json['queueId']), str(input_json['username'])
    
    try:
        queueupdate = container_queues.read_item(item=queueId, partition_key=queueId)
    
        if queueupdate['is_active'] == False:
            dictToReturn = {"message":"The queue is not active"}
            return jsonify(dictToReturn), 403

        if username in queueupdate["users"]:
            dictToReturn = {"message":"You are already in the queue"}
            return jsonify(dictToReturn), 403
        
        admin = queueupdate['admin']

        userupdate = container_users.read_item(item=admin, partition_key=admin)
        for q in range(len(userupdate['createdqueues'])):
            if userupdate['createdqueues'][q]['id'] == queueId:
                userupdate['createdqueues'][q]['users'].append(username)
                userupdate['createdqueues'][q]['count']+=1
                userupdate['createdqueues'][q]['total_time']+=userupdate['createdqueues'][q]['time_per_user_m']
                break
        

        container_users.replace_item(admin, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
        

        queueupdate["users"].append(username)
        queueupdate["count"] += 1
        queueupdate["total_time"] += queueupdate['time_per_user_m']
        
        try:
            userupdate = container_users.read_item(item=username, partition_key=username)

            qinfo = {
                'name':queueupdate['name'],
                'id':queueupdate['id'],
                'city':queueupdate['city'],
                'is_active':queueupdate['is_active'],
                'tag':queueupdate['tag'],
                'position':queueupdate['count'],
                'time':(queueupdate['count']-1)*queueupdate['time_per_user_m']
            }
            userupdate['activequeues'].append(qinfo)
            userupdate['nactivequeues'] += 1

            container_users.replace_item(username, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
        

        
        
        except Exception as e:
            return jsonify({"message":"Bad request"}), 404
        
        container_queues.replace_item(queueId, queueupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)

        dictToReturn = {"message":f"You have joined the queue successfully"}        
        return jsonify(dictToReturn), 201

    except:
        return jsonify({"message":"The queue doesn't exist"}), 404


# my position
@app.route('/api/myposition', methods=['POST'])
def mypos():
    input_json = request.get_json(force=True) 
    queueId, username = str(input_json['queueId']), str(input_json['username'])
    
    try:
        queueupdate = container_queues.read_item(item=queueId, partition_key=queueId)
    
        if username in queueupdate["users"]:
            userposition = queueupdate['users'].index(username)+1
            esttimereq = (userposition-1) * queueupdate['time_per_user_m']
            dictToReturn = {"message":f"success", "position":userposition, "estimatedtime":esttimereq}
            return jsonify(dictToReturn), 201
        else:
            return jsonify({"message":"You aren't in the queue"}), 404

    except:
        return jsonify({"message":"The queue doesn't exist"}), 404


# queue info
@app.route('/api/queueinfo', methods=['POST'])
def queueinfo():
    input_json = request.get_json(force=True) 

    queueId = str(input_json['queueId'])

    try:
        queueinfo1 = container_queues.read_item(item=queueId, partition_key=queueId)
        return jsonify(queueinfo1), 200

    except:
        return jsonify({"message":"The queue doesn't exist"}), 404


# leave queue
@app.route('/api/leavequeue', methods=['POST'])
def leavequeue():
    input_json = request.get_json(force=True) 

    queueId, username = str(input_json['queueId']), str(input_json['username']) 

    try:
        queueupdate = container_queues.read_item(item=queueId, partition_key=queueId)

        admin = queueupdate['admin']


        if username not in queueupdate['users']:
            return jsonify({"message":"You haven't joined the queue"}), 404

        inqueueusers = queueupdate['users']        
        
        try:

            # position of the person leaving the queue
            userleavingpos = inqueueusers.index(username)

            # updating pos and wait time for users after 
            for u in range(userleavingpos+1, len(inqueueusers)):
                userupdate = container_users.read_item(item=inqueueusers[u], partition_key=inqueueusers[u])
                for q in range(len(userupdate['activequeues'])):
                    if userupdate['activequeues'][q]['id'] == queueId:
                        userupdate['activequeues'][q]['position'] -= 1
                        userupdate['activequeues'][q]['time'] -= queueupdate['time_per_user_m']
                        break
                container_users.replace_item(inqueueusers[u], userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
            
            # removing line from username
            userupdate = container_users.read_item(item=username, partition_key=username)
            userupdate['nactivequeues'] -= 1
            for q in range(len(userupdate['activequeues'])):
                if userupdate['activequeues'][q]['id'] == queueId:
                    del userupdate['activequeues'][q]
                    break          

            container_users.replace_item(username, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)         


            # updating queue for admin
            userupdate = container_users.read_item(item=admin, partition_key=admin)
            for q in range(len(userupdate['createdqueues'])):
                if userupdate['createdqueues'][q]['id'] == queueId:
                    userupdate['createdqueues'][q]['count'] -= 1
                    userupdate['createdqueues'][q]['total_time'] -= userupdate['createdqueues'][q]['time_per_user_m']
                    userupdate['createdqueues'][q]['users'].remove(username)
                    break
            
            container_users.replace_item(admin, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
            
        except:
            return jsonify({"message":"Bad request"}), 404

        queueupdate['users'].remove(username)
        queueupdate["count"] -= 1
        queueupdate["total_time"] -= queueupdate["time_per_user_m"]
        
        container_queues.replace_item(queueId, queueupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)


        return jsonify({"message":"You have successfully left the queue"}), 201

    except:
        return jsonify({"message":"The queue doesn't exist"}), 404


# go next in line 
@app.route('/api/gonext', methods=['POST'])
def gonext():
    input_json = request.get_json(force=True) 
    
    queueId = str(input_json['queueId'] )

    try:
        queueupdate = container_queues.read_item(item=queueId, partition_key=queueId)
        
        if queueupdate['count'] == 0:
            return jsonify({"message":"The queue is empty"}), 403
        

        inqueueusers = queueupdate['users'][1:]
        username = queueupdate['users'][0]

        # updating pos and wait time for users after 
        for u in range(len(inqueueusers)):
            userupdate = container_users.read_item(item=inqueueusers[u], partition_key=inqueueusers[u])
            for q in range(len(userupdate['activequeues'])):
                if userupdate['activequeues'][q]['id'] == queueId:
                    userupdate['activequeues'][q]['position'] -= 1
                    userupdate['activequeues'][q]['time'] -= queueupdate['time_per_user_m']
                    break
            container_users.replace_item(inqueueusers[u], userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
        
        # removing queue from username
        userupdate = container_users.read_item(item=username, partition_key=username)
        userupdate['nactivequeues'] -= 1
        for q in range(len(userupdate['activequeues'])):
            if userupdate['activequeues'][q]['id'] == queueId:
                del userupdate['activequeues'][q]
                break          

        container_users.replace_item(username, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)             


        # updating queue for admin
        admin = queueupdate['admin']

        userupdate = container_users.read_item(item=admin, partition_key=admin)

        for q in range(len(userupdate['createdqueues'])):

            if userupdate['createdqueues'][q]['id'] == queueId:

                userupdate['createdqueues'][q]['count'] -= 1
                del userupdate['createdqueues'][q]['users'][0]
                userupdate['createdqueues'][q]['total_time'] -= queueupdate['time_per_user_m']
                break
                
        
        container_users.replace_item(admin, userupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)
            


        queueupdate['users'] = inqueueusers
        queueupdate["count"] -= 1
        queueupdate["total_time"] -= queueupdate["time_per_user_m"]

        
        container_queues.replace_item(queueId, queueupdate, populate_query_metrics=None, pre_trigger_include=None, post_trigger_include=None)

        dictToReturn = {"message":"Success"}
        return jsonify(dictToReturn), 201

    except Exception as e:
        print(e)
        return jsonify({"message":"The queue doesn't exist"}), 404
