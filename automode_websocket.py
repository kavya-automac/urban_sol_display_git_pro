import asyncio
import json
import random
import tracemalloc

import websockets
from urllib.parse import parse_qs, urlparse
import threading
import time
from datetime import datetime
# import pymodbus.client.serial as ModbusClient
from pymodbus.client import AsyncModbusSerialClient
# from pymodbus.transaction import ModbusRtuFramer
import asyncio


async def run_modbus_client():

    global client
    client = AsyncModbusSerialClient(method='rtu', port="COM6", baudrate=9600, parity='E', stopbits=1)
    # client = ModbusClient.ModbusSerialClient(type='rtu', port='COM6', parity='E', baudrate=9600, stopbits=1, bytesize=8)
    con = await client.connect()
    print("connectedd", con)
# asyncio.run(run_modbus_client())


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


# Define the time intervals in seconds
cycle_time = updated_data["total_cycle_time"]  # 5 minutes in seconds
motor_rev_time = updated_data["motor_rev_time"]  # 10 seconds
wait_time_rev = updated_data["rev_wait_time"]  # 5 seconds
motor_fwd_time = updated_data["motor_fwd_time"]  # 20 seconds
wait_time_fwd = updated_data["fwd_wait_time"]  # 5 seconds
cycle_wait_time = updated_data["wait_time_in_cycles"]  # 5 seconds
blower_time = updated_data["blower"]




no_of_cycles = updated_data["no_of_cycles"]
cycle_count=0
# Global variables
end_time = None  # To hold the end time of the cycle
pause_duration = 0  # To track the total pause duration



async def motor_rev(end_time):
    print('rev beore writing', datetime.now().isoformat())
    await client.write_coils(1280, [0,1], slave=0x01)
    # write_single_coil_response =client.write_coils(1280,[0,1] , unit=0x01)
    # write_single_coil_response = client.write_coil(1281, 1, unit=0x01)
    print('rev after writing', datetime.now().isoformat())
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
                await asyncio.sleep(1)
                json_data = get_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming motor reverse", datetime.now().isoformat())
        await asyncio.sleep(1)
    print(datetime.now().isoformat(), "- > Motor reverse complete")


async def wait_period(wait_time, end_time):
    print('wait beore writing',datetime.now().isoformat())
    await client.write_coils(1280, [0,0], slave=0x01)


    # client.write_coils(1280,[0,0] , unit=0x01)
    # client.write_coil(1281, 0, unit=0x01)
    print('wait after writing', datetime.now().isoformat())
    global pause_duration
    print(datetime.now().isoformat(), "- > Waiting...")
    for _ in range(wait_time):

        if time.time() >= end_time:
            print("Stopping wait_period due to end time")
            break
        json_data = get_json_data()
        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in wait period",datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = get_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming wait", datetime.now().isoformat())
        await asyncio.sleep(1)
    print(datetime.now().isoformat(), "- > Wait complete")


async def blower_off(delay):
    print("blower  before on",datetime.now().isoformat())

    await asyncio.sleep(delay)
    await client.write_coil(1282, 0, slave=0x01)
    print("blower off",datetime.now().isoformat())






async def motor_fwd(end_time):
    print('fwd beore writing',datetime.now().isoformat())
    await client.write_coils(1280, [1,0,1], slave=0x01)
    # await client.write_coils(1282, [1,0], slave=0x01)

    asyncio.create_task(blower_off(blower_time))






    # write_single_coil_response = client.write_coils(1280,[1,0] , unit=0x01)
    # write_single_coil_response = client.write_coil(1281, 0, unit=0x01)
    print('fwd after writing', datetime.now().isoformat())
    global pause_duration
    print(datetime.now().isoformat(), "- > Motor running forward")
    for _ in range(motor_fwd_time):

        if time.time() >= end_time:
            print("Stopping motor_fwd due to end time")
            break
        json_data = get_json_data()
        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in motor fwd",datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = get_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming motor forward", datetime.now().isoformat())
        await asyncio.sleep(1)
    print(datetime.now().isoformat(), "- > Motor forward complete")


async def on_receive(message):
    try:
        print(f"Received message: {message}")
        settings_msg_data = json.loads(message)
        update_json_data(settings_msg_data)
    except Exception as e:
        print(f"Error processing message: {e}")


async def handle_messages(websocket):
    print('websocket',websocket)
    async for message in websocket:
        print('message',message)
        await on_receive(message)


async def run_cycle(websocket, path):
    query_params = parse_qs(urlparse(path).query)
    if query_params['screen'][0] == "Settings":
        sending_data = get_json_data()
        await websocket.send(json.dumps(sending_data))

        try:
            settings_msg = await asyncio.wait_for(websocket.recv(), timeout=3)
            print('settings_msg',settings_msg)
            await on_receive(settings_msg)
            sending_data_u = get_json_data()
            await websocket.send(json.dumps(sending_data_u))
        except Exception as e:
            print('e in settings', e)

    if query_params['screen'][0] == "Operations":
        try:
            operation_cycle_start = await asyncio.wait_for(websocket.recv(), timeout=3)
            await on_receive(operation_cycle_start)

            json_data = get_json_data()
            if json_data.get("Cycle_start") == "On":
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

                # Start the message handling task
                message_task = asyncio.create_task(handle_messages(websocket))

                while time.time() < end_time:
                    # print('no_of_cycles', no_of_cycles)
                    print("in while",datetime.now().isoformat())

                    await motor_fwd(end_time)
                    await wait_period(wait_time_fwd, end_time)
                    await motor_rev(end_time)
                    await wait_period(wait_time_rev, end_time)

                    cycle_count += 1

                    if no_of_cycles == cycle_count:
                        await wait_period(cycle_wait_time, end_time)
                        cycle_count = 0

                    if pause_duration > 0:
                        print('pause_duration after updation', pause_duration)
                        end_time += pause_duration
                        pause_duration = 0  # Reset pause duration

                    if time.time() >= end_time:
                        print("Cycle end time reached:", end_iso)
                        print("Ending process at:", datetime.now().isoformat())
                        await client.write_coil(1282, 0, slave=0x01)

                        break

                # Cancel the message handling task
                message_task.cancel()
                try:
                    await message_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            print('e operation', e)




async def main():
    # Enable tracemalloc
    tracemalloc.start()

    # Run the Modbus client
    await run_modbus_client()

    # Start the WebSocket server
    server = await websockets.serve(run_cycle, "192.168.29.144", 8765)

    # Run the WebSocket server until the application is terminated
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
