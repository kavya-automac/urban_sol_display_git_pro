import json
import logging
import asyncio

import websocket
import websockets
import datetime
from urllib.parse import parse_qs, urlparse
from pymodbus.client import AsyncModbusSerialClient
import time
# read plc addresses and loads the data
from datetime import datetime

logging.basicConfig(level=logging.INFO)


async def run_modbus_client():
    try:

        global client
        client = AsyncModbusSerialClient(method='rtu', port="COM7", baudrate=9600, parity='E', stopbits=1)
        # client = ModbusClient.ModbusSerialClient(type='rtu', port='COM6', parity='E', baudrate=9600, stopbits=1, bytesize=8)
        con = await client.connect()
        print("connectedd", con)
        # pop_ups = False
        # await websocket.send(json.dumps({"Pop_up": pop_ups}))

    except Exception as e:
        print("exception in modbus connection",e)
        # pop_ups = True
        # await websocket.send(json.dumps({"Pop_up": pop_ups, "message":str(type(e).__name__)}))


        print("connection exception",e)






plc_json_file_path = 'plc_registers_addresses.json'

# Function to load JSON data from a file


def plc_address_load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

interlock_json_file_path = 'interlocks.json'


def interlock_load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data


plc_json_data = plc_address_load_json(plc_json_file_path)


async def get_interlock_json_data():
    return interlock_load_json(interlock_json_file_path)


def interlock_save_json(file_path, data):
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)



async def interlock_update_json_data(settings_msg_data):
    json_data = await get_interlock_json_data()
    for key, value in settings_msg_data.items():
        if key in json_data:
            json_data[key] = value
    interlock_save_json(interlock_json_file_path, json_data)



def interlocks_should_pause(json_data):
    return (json_data["door_open"] or
            # json_data["Cycle_stop"] or
            json_data["blower"] > 50 or
            json_data["temp_lower_limit"] > 50)


updated_interlock_data =  asyncio.run(get_interlock_json_data())

cycle_time = updated_interlock_data["total_cycle_time"]  # 5 minutes in seconds
motor_rev_time = updated_interlock_data["motor_rev_time"]  # 10 seconds
wait_time_rev = updated_interlock_data["rev_wait_time"]  # 5 seconds
motor_fwd_time = updated_interlock_data["motor_fwd_time"]  # 20 seconds
wait_time_fwd = updated_interlock_data["fwd_wait_time"]  # 5 seconds
cycle_wait_time = updated_interlock_data["wait_time_in_cycles"]  # 5 seconds
blower_time = updated_interlock_data["blower"]

no_of_cycles = updated_interlock_data["no_of_cycles"]
cycle_count=0
# Global variables
end_time = None  # To hold the end time of the cycle
pause_duration = 0  # To track the total pause duration

global pop_ups
pop_ups=None

async def motor_rev(end_time,websocket):
    print('rev beore writing', datetime.now().isoformat())
    try:

        await client.write_coils(1280, [0,1], slave=0x01)
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))
    except  Exception as e:
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message":str(type(e).__name__)}))
        print("Exception in motor rev write coils",e)
    # write_single_coil_response =client.write_coils(1280,[0,1] , unit=0x01)
    # write_single_coil_response = client.write_coil(1281, 1, unit=0x01)
    print('rev after writing', datetime.now().isoformat())
    global pause_duration
    print(datetime.now().isoformat(), "- > Motor running in reverse")
    for _ in range(motor_rev_time):

        if time.time() >= end_time:
            print("Stopping motor_rev due to end time")
            break
        json_data = await get_interlock_json_data()
        if json_data.get("Cycle_status") == "Off":
            print('motor rev stoped break')
            break

        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in motor rev", datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = await get_interlock_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming motor reverse", datetime.now().isoformat())
        await asyncio.sleep(1)
    print(datetime.now().isoformat(), "- > Motor reverse complete")


async def wait_period(wait_time, end_time,websocket):
    print('wait beore writing',datetime.now().isoformat())
    try:

        await client.write_coils(1280, [0,0], slave=0x01)
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))

    except Exception as e:
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))
        print('Exception wait period write coils',e)
    print('wait after writing', datetime.now().isoformat())
    global pause_duration
    print(datetime.now().isoformat(), "- > Waiting...")
    for _ in range(wait_time):

        if time.time() >= end_time:
            print("Stopping wait_period due to end time")
            break
        json_data = await get_interlock_json_data()
        if json_data.get("Cycle_status") == "Off":
            print('wait period stoped break')
            break
        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in wait period",datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = await get_interlock_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming wait", datetime.now().isoformat())
        await asyncio.sleep(1)
    print(datetime.now().isoformat(), "- > Wait complete")


async def blower_off(delay,websocket):
    print("blower  before on",datetime.now().isoformat())
    await asyncio.sleep(delay)
    try:

        await client.write_coil(1282, 0, slave=0x01)
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))
    except Exception as e:
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message":str(type(e).__name__)}))
        print("Exception in blower off ",e)
    print("blower off",datetime.now().isoformat())


async def motor_fwd(end_time,websocket):
    print('fwd beore writing',datetime.now().isoformat())
    try:

        await client.write_coils(1280, [1,0,1], slave=0x01)
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))
    except Exception as e:
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))

        print("Exception in motor fwd write coils",e)
    print("aftervtry exception")
    asyncio.create_task(blower_off(blower_time,websocket))

    print('fwd after writing', datetime.now().isoformat())
    global pause_duration
    print(datetime.now().isoformat(), "- > Motor running forward")
    for _ in range(motor_fwd_time):

        if time.time() >= end_time:
            print("Stopping motor_fwd due to end time")
            break
        json_data = await get_interlock_json_data()
        if json_data.get("Cycle_status") == "Off":
            print('motor fwd stoped break')
            break

        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in motor fwd",datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = await get_interlock_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming motor forward", datetime.now().isoformat())
        await asyncio.sleep(1)
    print(datetime.now().isoformat(), "- > Motor forward complete")






async def on_receive(message):
    try:
        print(f"Received message: {message}")
        settings_msg_data = json.loads(message)
        await interlock_update_json_data(settings_msg_data)
    except Exception as e:
        # pop_ups = True
        # await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e)), "Exception": str(e)}))

        print(f"Error processing message: {e}")


async def handle_messages(websocket):
    print('websocket',websocket)
    async for message in websocket:
        print('message',message)
        await on_receive(message)







async def get_inputs(websocket):

    input_data = plc_json_data["inputs"]
    ip_dict = {}
    try:

        for k, v in input_data.items():

            inputs = await client.read_discrete_inputs(v, 1, slave=0x01)
            # print('inputs',inputs,k,v)
            # print('inputs bits',inputs.bits)
            ip_dict[k] = inputs.bits[0]
        print('input result', ip_dict)
        pop_ups = False
        await websocket.send(
            json.dumps({"Pop_up": pop_ups}))

        return ip_dict
    except Exception as e:
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))

        print("input exception",e)

        return {
            "MMtrip": False,
            "BMT": False,
            "DoorOpen": False,
            "SppOk": False,
            "Eswitch": True
        }

# reading ouput addresses data

async def get_output(websocket):

    output_data = plc_json_data["outputs"]
    # print('..',output_data)
    op_dict = {}

    try:

        for k,v in output_data.items():
            outputs = await client.read_coils(v, 1, slave=0x01)
            op_dict[k] = outputs.bits[0]
        # print('op_result',op_dict)
        pop_ups = False
        await websocket.send(
            json.dumps({"Pop_up": pop_ups}))

        return op_dict
    except Exception as e:
        print("Exception in output....", e)
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))


        return {
            "MMF": True,
            "MMR": False,
            "Blower_Motor": True,
            "Heater": False,
            "Acr": False
        }



async def IO_screen(websocket):
    print("ioscreen")
    try:
        pop_ups = False
        await websocket.send(
            json.dumps({"Pop_up": pop_ups}))
        while True:
            ip_data = await get_inputs(websocket)
            op_data = await get_output(websocket)
            Data = {**ip_data, **op_data}  # merege 2 dicts
            print('data',Data)
            await websocket.send(json.dumps(Data))

            # Wait for one second before sending the next message
            await asyncio.sleep(1)
    except Exception as e:  # disconnect line
        pop_ups = True
        await websocket.send(
            json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))

        print("Client disconnected")

async def Manual_screen(websocket):
    print("manual")
    try:
        # pop_ups = False
        # await websocket.send(json.dumps({"Pop_up": pop_ups}))

        while True:
            screen2_op_data = await get_output(websocket)  # only outputs
            await websocket.send(json.dumps(screen2_op_data))
            # print("after sending")
            try:

                # in client data data should be like {"MMT":0} in messages value should be 0 or 1
                client_data = await asyncio.wait_for(websocket.recv(),
                                                     timeout=3)  # waiting for data(message) from websockets
                print('client_data', client_data)

                #  first keys from json file
                get_key = list(json.loads(client_data).keys())[0]

                # getting key name

                plc_coil_reg = plc_json_data["outputs"][get_key]

                # using key getting value here
                plc_coil_reg_val = json.loads(client_data)[get_key]
                pop_ups = False
                await websocket.send(json.dumps({"Pop_up": pop_ups}))


                try:
                    if get_key == "MMF" and plc_coil_reg_val == 1:
                        print('before mmf write', datetime.now().isoformat())
                        try:

                            mmf_coil_write = await client.write_coil(1280, plc_coil_reg_val, slave=0x01)
                            mmf_coil_write = await client.write_coil(1281, 0, slave=0x01)
                            pop_ups = False
                            await websocket.send(json.dumps({"Pop_up": pop_ups}))
                        except Exception as e:

                            pop_ups = True
                            await websocket.send(
                                json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))

                            print("changes done in MMF write", e)
                        print('after mmf write', datetime.now().isoformat())
                    elif get_key == "MMR" and plc_coil_reg_val == 1:
                        try:

                            mmr_coil_write = await client.write_coil(1281, plc_coil_reg_val, slave=0x01)
                            mmr_coil_write = await client.write_coil(1280, 0, slave=0x01)
                            pop_ups = False
                            await websocket.send(json.dumps({"Pop_up": pop_ups}))
                        except Exception as e:
                            pop_ups = True
                            await websocket.send(
                                json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))

                            print("changes done in MMR ", e)
                    else:
                        print('...b....', get_key, datetime.now().isoformat())
                        try:

                            out_write = await client.write_coil(plc_coil_reg, plc_coil_reg_val, slave=0x01)
                            pop_ups = False
                            await websocket.send(json.dumps({"Pop_up": pop_ups}))
                        except Exception as e:
                            pop_ups = True
                            await websocket.send(
                                json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))

                            print("Exception in manual any other key changes", e)
                        print('...b....', datetime.now().isoformat())
                        print('out_write', out_write)
                except Exception as e:
                    pop_ups = True
                    await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))

                    print("except mmf mmr ", e)

                # try:
                #     print('...b....',get_key, datetime.now().isoformat())
                #     out_write = await client.write_coil(plc_coil_reg, plc_coil_reg_val, slave=0x01)
                #     print('...b....', datetime.now().isoformat())
                #     print('out_write',out_write)
                # except Exception as e :
                #     print('e screen 2',e)


            except Exception as e:

                print("in except")
                # No data received from the client within the timeout period
    except Exception as e :  # disconnect line
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__)}))

        print("Client disconnected screen 2")


async def Settings_screen(websocket):
    print("settings",websocket)
    sending_data = await get_interlock_json_data()
    await websocket.send(json.dumps(sending_data))
    # print(await asyncio.wait_for(websocket.recv(), timeout=3))

    try:
        print("sssstry")

        settings_msg = await asyncio.wait_for(websocket.recv(), timeout=3)
        # print('settings_msg', settings_msg)
        await on_receive(settings_msg)
        sending_data_u = await get_interlock_json_data()
        await websocket.send(json.dumps(sending_data_u))
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))

    except Exception as e:
        # pop_ups = True
        # await websocket.send(json.dumps({"Pop_up": pop_ups, "message":str(type(e).__name__)}))

        print('e in settings', e)

async def Operations_screen(websocket):
    print("Operations")
    json_data = await get_interlock_json_data()
    print("json_data", json_data)
    await websocket.send(json.dumps({"Cycle_status": json_data["Cycle_status"]}))
    try:

        operation_cycle_start = await asyncio.wait_for(websocket.recv(), timeout=10)

        print('operation_cycle_start',operation_cycle_start)
        await on_receive(operation_cycle_start)

        json_data = await get_interlock_json_data()
        # print("json_data",json_data)
        # await websocket.send(json.dumps({"Cycle_status":json_data["Cycle_status"]}))
        if json_data.get("Cycle_status") == "On":
            await websocket.send(json.dumps("process_started"))
            await websocket.send(json.dumps({"Cycle_status": json_data["Cycle_status"]}))
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
            print('messagetask', message_task)

            while time.time() < end_time:

                print("in while", datetime.now().isoformat())

                await motor_fwd(end_time,websocket)
                await wait_period(wait_time_fwd, end_time,websocket)
                await motor_rev(end_time,websocket)
                await wait_period(wait_time_rev, end_time,websocket)

                cycle_count += 1

                if no_of_cycles == cycle_count:
                    await wait_period(cycle_wait_time, end_time,websocket)
                    cycle_count = 0

                if pause_duration > 0:
                    print('pause_duration after updation', pause_duration)
                    end_time += pause_duration
                    pause_duration = 0  # Reset pause duration
                json_data1 = await get_interlock_json_data()  # Refresh JSON data
                if json_data1.get("Cycle_status") == "Off":
                    await websocket.send(json.dumps({"Cycle_status": json_data1["Cycle_status"]}))
                    print('Cycle stop received, breaking out of the loop')

                    break

                if time.time() >= end_time:
                    print("Cycle end time reached:", end_iso)
                    print("Ending process at:", datetime.now().isoformat())
                    await client.write_coil(1282, 0, slave=0x01)

                    break

            # json_data2 = get_interlock_json_data()
            # json_data2["Cycle_stop"] = False
            # interlock_update_json_data(json_data2)
            pop_ups = False
            await websocket.send(json.dumps({"Pop_up": pop_ups}))
            # json_data2 = get_interlock_json_data()
            # json_data2["Cycle_status"] = "Off"
            # await interlock_update_json_data(json_data2)
            # print('outof the loop 22')
            # Cancel the message handling task
            message_task.cancel()
            try:
                await message_task
            except asyncio.CancelledError:
                pass
    except Exception as e:
        # pop_ups=True
        # await websocket.send(json.dumps({"Pop_up":pop_ups,"message":str(type(e).__name__)}))
        print('e operation',e,",,,,,,,,,,,,,,,," ,type(e))

async def echo(websocket, path):
    try:
        query_params = parse_qs(urlparse(path).query)

        if query_params['screen'][0] == "InputOutput":  # InputOutput
            await IO_screen(websocket)
        if query_params['screen'][0] == "Manual":
            await Manual_screen(websocket)
        if query_params['screen'][0] == "Settings":
            await Settings_screen(websocket)
        if query_params['screen'][0] == "Operations":
            await Operations_screen(websocket)



    except websockets.ConnectionClosed as e:
        logging.error(f"Connection closed: {e.code} - {e.reason}")
    except websockets.InvalidMessage as e:
        logging.error(f"Invalid message received: {e}")
    except websockets.WebSocketTimeout as e:
        logging.error(f"WebSocket operation timed out: {e}")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")


async def main():
    try:
        async with websockets.serve(echo, "192.168.29.144", 8765):
            logging.info("WebSocket server started on ws://192.168.29.144:8765")
            client = None
            print("client in main...", client)
            logging.error(f'client{client}')
            client = await run_modbus_client()




            await asyncio.Future()  # run forever
    except websockets.WebSocketException as e:
        logging.error(f"WebSocket server error: {e}")
    except Exception as e:
        logging.error(f"Unexpected error during server start: {e}")


    # global client
    # client = None
    # print("client in main",client)
    # logging.error(f'client{client}')
    # try:
    #     if client is None:
    #         # print("modbus client connection")
    #         client = await run_modbus_client()
    # except Exception as e:
    #     print("modbus connection eroor",e)

if __name__ == "__main__":
    asyncio.run(main())




