

import asyncio
import json
import random

import websockets
from urllib.parse import parse_qs, urlparse
import pymodbus.client.serial as ModbusClient
import threading
import time
from datetime import datetime
import json

json_file_path = 'interlocks.json'

def load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data


def save_json(file_path, data):
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)


def get_json_data():
    return load_json(json_file_path)

def interlocks_should_pause(json_data):
    return (json_data["door_open"] or
            # json_data["heater"] > 50 or
            json_data["Cycle_stop"] or
            json_data["blower"] > 50 or
            json_data["temp_lower_limit"] > 50)
def update_json_data(settings_msg_data):
    json_data = get_json_data()
    for key, value in settings_msg_data.items():
        if key in json_data:
            json_data[key] = value
    save_json(json_file_path, json_data)

updated_data = get_json_data()


# {
#    "door_open": false,
#     "total_cycle_time": 300,
#     "motor_fwd_time": 20,
#     "fwd_wait_time": 5,
#     "motor_rev_time": 10,
#     "rev_wait_time": 5,
#      "wait_time_in_cycles": 5,
#      "blower": 5,
#     "compost_out_time": 10,
#     "temp_lower_limit": 10,
#     "temp_upper_limit": 10,
#   "no_of_cycles": 5,






# Define the time intervals in seconds
cycle_time = updated_data["total_cycle_time"]  # 5 minutes in seconds
motor_rev_time = updated_data["motor_rev_time"]  # 10 seconds
wait_time_rev = updated_data["rev_wait_time"]  # 5 seconds
motor_fwd_time = updated_data["motor_fwd_time"]  # 20 seconds
wait_time_fwd = updated_data["fwd_wait_time"]  # 5 seconds
cycle_wait_time = updated_data["wait_time_in_cycles"]  # 5 seconds

no_of_cycles = updated_data["no_of_cycles"]
cycle_count=0
# Global variables
end_time = None  # To hold the end time of the cycle
pause_duration = 0  # To track the total pause duration

def motor_rev():
    global pause_duration
    print(datetime.now().isoformat(), "- > Motor running in reverse")
    for _ in range(motor_rev_time):
        if time.time() >= end_time:
            print("Stopping motor_rev due to end time")
            break
        json_data = get_json_data()
        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in motor rev", datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                time.sleep(1)
                json_data = get_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming motor reverse", datetime.now().isoformat())
        time.sleep(1)
    print(datetime.now().isoformat(), "- > Motor reverse complete")

def wait_period(wait_time):
    global pause_duration
    print(datetime.now().isoformat(), "- > Waiting...")
    for _ in range(wait_time):
        if time.time() >= end_time:
            print("Stopping wait_period due to end time")
            break
        json_data = get_json_data()
        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in wait period", datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                time.sleep(1)
                json_data = get_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming wait", datetime.now().isoformat())
        time.sleep(1)
    print(datetime.now().isoformat(), "- > Wait complete")

def motor_fwd():
    global pause_duration
    print(datetime.now().isoformat(), "- > Motor running forward")
    for _ in range(motor_fwd_time):
        if time.time() >= end_time:
            print("Stopping motor_fwd due to end time")
            break
        json_data = get_json_data()
        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in motor fwd", datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                time.sleep(1)
                json_data = get_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming motor forward", datetime.now().isoformat())
        time.sleep(1)
    print(datetime.now().isoformat(), "- > Motor forward complete")


async def run_cycle(websocket, path):
    query_params = parse_qs(urlparse(path).query)
    if query_params['screen'][0] == "Settings":
        #
        # {
        #     "total_cycle_time": 300,
        #     "blower": 5
        # }

        sending_data = get_json_data()

        # await websocket.send(sending_data)
        await websocket.send(json.dumps(sending_data))

        try:
            settings_msg = await asyncio.wait_for(websocket.recv(), timeout=3)  # waiting for data(message) from websockets
            print('operation_cycle_start', settings_msg)
            settings_msg_data=json.loads(settings_msg)
            print('load_operation_data', settings_msg)
            update_json_data(settings_msg_data)

            sending_data_u = get_json_data()

            # await websocket.send(sending_data)
            await websocket.send(json.dumps(sending_data_u))

        except Exception as e:
            print('e in settings',e)


    if query_params['screen'][0] == "Operation":


        try:

            operation_cycle_start = await asyncio.wait_for(websocket.recv(), timeout=3)  # waiting for data(message) from websockets
            print('operation_cycle_start', operation_cycle_start)
            load_operation_data=json.loads(operation_cycle_start)

            print('load_operation_data', load_operation_data)
            # {
            #     "Cycle_start": "On"
            # }

            if load_operation_data["Cycle_start"] == "On":
                await websocket.send(json.dumps("process_started"))
                global end_time
                global pause_duration
                global cycle_count

                start_time = time.time()
                end_time = start_time + cycle_time

                start_datetime = datetime.fromtimestamp(start_time)
                end_datetime = datetime.fromtimestamp(end_time)

                start_iso = start_datetime.isoformat()
                end_iso = end_datetime.isoformat()

                print("Start Time (ISO 8601 format):", start_iso)
                print("End Time (ISO 8601 format):", end_iso)



                while time.time() < end_time:


                    print('no_of_cycles', no_of_cycles)
                    # for _ in range(no_of_cycles):
                    print(datetime.now().isoformat())
                    json_data = get_json_data()
                    print('Current conditions:', json_data)
                    motor_fwd_thread = threading.Thread(target=motor_fwd)
                    motor_fwd_thread.start()
                    motor_fwd_thread.join()

                    wait_thread = threading.Thread(target=wait_period,args=(wait_time_fwd,))
                    wait_thread.start()
                    wait_thread.join()

                    motor_rev_thread = threading.Thread(target=motor_rev)
                    motor_rev_thread.start()
                    motor_rev_thread.join()

                    wait_thread = threading.Thread(target=wait_period,args=(wait_time_rev,))
                    wait_thread.start()
                    wait_thread.join()
                    print('cycle_count before inc', cycle_count)

                    cycle_count = cycle_count + 1
                    print('cycle_count after inc', cycle_count)

                    if no_of_cycles == cycle_count:
                        wait_thread = threading.Thread(target=wait_period,args=(cycle_wait_time,))
                        wait_thread.start()
                        wait_thread.join()

                        print('cycle_count equal no_of_cycle', cycle_count)

                        cycle_count = 0




                    if pause_duration > 0:
                        print('pause_duration after updation', pause_duration)
                        end_time += pause_duration
                        pause_duration = 0  # Reset pause duration

                    if time.time() >= end_time:
                        print("Cycle end time reached:", end_iso)
                        print("Ending process at:", datetime.now().isoformat())
                        break



                else:
                    pass

                    # load_operation_data = json.loads(operation_cycle_start)
                    #
                    print('load_operation_data else', load_operation_data)
                    update_json_data(load_operation_data)


        except Exception as e:
                print('e operation',e)



if __name__ == "__main__":
    server = websockets.serve(run_cycle, "192.168.29.144", 8765)

    asyncio.get_event_loop().run_until_complete(server)
    asyncio.get_event_loop().run_forever()
