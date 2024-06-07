import asyncio
import json
import tracemalloc

import websockets
import datetime
from urllib.parse import parse_qs, urlparse
from pymodbus.client import AsyncModbusSerialClient
import time
# read plc addresses and loads the data
from datetime import datetime


async def run_modbus_client():
    try:

        global client
        client = AsyncModbusSerialClient(method='rtu', port="COM6", baudrate=9600, parity='E', stopbits=1)
        # client = ModbusClient.ModbusSerialClient(type='rtu', port='COM6', parity='E', baudrate=9600, stopbits=1, bytesize=8)
        con = await client.connect()
        print("connectedd", con)
    except Exception as e:
        print("connection exception",e)






plc_json_file_path = 'plc_registers_addresses.json'

# Function to load JSON data from a file


def plc_address_load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data


# read all the parameters of settings screen and interlocks

interlock_json_file_path = 'interlocks.json'


def interlock_load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data


plc_json_data = plc_address_load_json(plc_json_file_path)



def get_interlock_json_data():
    return interlock_load_json(interlock_json_file_path)


def interlock_save_json(file_path, data):
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)



def interlock_update_json_data(settings_msg_data):
    json_data = get_interlock_json_data()
    for key, value in settings_msg_data.items():
        if key in json_data:
            json_data[key] = value
    interlock_save_json(interlock_json_file_path, json_data)



def interlocks_should_pause(json_data):
    return (json_data["door_open"] or
            # json_data["Cycle_stop"] or
            json_data["blower"] > 50 or
            json_data["temp_lower_limit"] > 50)


updated_interlock_data = get_interlock_json_data()

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




async def motor_rev(end_time):
    print('rev beore writing', datetime.now().isoformat())
    try:
        await client.write_coils(1280, [0,1], slave=0x01)
    except  Exception as e:
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
        json_data = get_interlock_json_data()
        if json_data.get("Cycle_status") == "Off":
            print('motor rev stoped break')
            break

        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in motor rev", datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = get_interlock_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming motor reverse", datetime.now().isoformat())
        await asyncio.sleep(1)
    print(datetime.now().isoformat(), "- > Motor reverse complete")


async def wait_period(wait_time, end_time):
    print('wait beore writing',datetime.now().isoformat())
    try:
        await client.write_coils(1280, [0,0], slave=0x01)
    except Exception as e:
        print('Exception wait period write coils',e)
    print('wait after writing', datetime.now().isoformat())
    global pause_duration
    print(datetime.now().isoformat(), "- > Waiting...")
    for _ in range(wait_time):

        if time.time() >= end_time:
            print("Stopping wait_period due to end time")
            break
        json_data = get_interlock_json_data()
        if json_data.get("Cycle_status") == "Off":
            print('wait period stoped break')
            break
        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in wait period",datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = get_interlock_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming wait", datetime.now().isoformat())
        await asyncio.sleep(1)
    print(datetime.now().isoformat(), "- > Wait complete")


async def blower_off(delay):
    print("blower  before on",datetime.now().isoformat())
    await asyncio.sleep(delay)
    try:
        await client.write_coil(1282, 0, slave=0x01)
    except Exception as e:
        print("Exception in blower off ",e)
    print("blower off",datetime.now().isoformat())


async def motor_fwd(end_time):
    print('fwd beore writing',datetime.now().isoformat())
    try:
        await client.write_coils(1280, [1,0,1], slave=0x01)
    except Exception as e:
        print("Exception in motor fwd write coils",e)

    asyncio.create_task(blower_off(blower_time))

    print('fwd after writing', datetime.now().isoformat())
    global pause_duration
    print(datetime.now().isoformat(), "- > Motor running forward")
    for _ in range(motor_fwd_time):

        if time.time() >= end_time:
            print("Stopping motor_fwd due to end time")
            break
        json_data = get_interlock_json_data()
        if json_data.get("Cycle_status") == "Off":
            print('motor fwd stoped break')
            break

        if interlocks_should_pause(json_data):
            pause_start = time.time()
            print("Pausing due to condition in motor fwd",datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = get_interlock_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            print("Resuming motor forward", datetime.now().isoformat())
        await asyncio.sleep(1)
    print(datetime.now().isoformat(), "- > Motor forward complete")


async def on_receive(message):
    try:
        print(f"Received message: {message}")
        settings_msg_data = json.loads(message)
        interlock_update_json_data(settings_msg_data)
    except Exception as e:
        print(f"Error processing message: {e}")


async def handle_messages(websocket):
    print('websocket',websocket)
    async for message in websocket:
        print('message',message)
        await on_receive(message)





# reading input addresses data from plc

async def get_inputs():

    input_data = plc_json_data["inputs"]
    ip_dict = {}
    try:
        for k, v in input_data.items():

            inputs = await client.read_discrete_inputs(v, 1, slave=0x01)
            # print('inputs',inputs,k,v)
            # print('inputs bits',inputs.bits)
            ip_dict[k] = inputs.bits[0]
        print('input result', ip_dict)

        return ip_dict
    except Exception as e:
        print("input exception",e)
        # return {
        #     "MMtrip": False,
        #     "BMT": False,
        #     "DoorOpen": False,
        #     "SppOk": False,
        #     "Eswitch": True
        # }

# reading ouput addresses data

async def get_output():

    output_data = plc_json_data["outputs"]
    # print('..',output_data)
    op_dict = {}
    try:
        for k,v in output_data.items():
            outputs = await client.read_coils(v, 1, slave=0x01)
            op_dict[k] = outputs.bits[0]
        # print('op_result',op_dict)

        return op_dict
    except Exception as e:
        print("Exception in output",e)
        # return {
        #     "MMF": True,
        #     "MMR": False,
        #     "Blower_Motor": True,
        #     "Heater": False,
        #     "Acr": False
        # }


async def Screens_websocket_main(websocket, path):
    # Parse query parameters from the path

    query_params = parse_qs(urlparse(path).query)
    # print('query_params',query_params)
    # print('query_params type',type(query_params))

    # print('query_params',query_params['machine_id'][0])

    if query_params['screen'][0]=="InputOutput": #InputOutput
        try:
            while True:
                ip_data = await get_inputs()
                op_data = await get_output()
                Data =  {**ip_data, **op_data} #merege 2 dicts
                # print('data',Data)
                await websocket.send(json.dumps(Data))

                # Wait for one second before sending the next message
                await asyncio.sleep(1)
        except websockets.exceptions.ConnectionClosed:  # disconnect line
            print("Client disconnected")

    elif query_params['screen'][0]=="Manual":#Manual

        try:
            while True:
                screen2_op_data = await get_output() # only outputs
                await websocket.send(json.dumps(screen2_op_data))
                # print("after sending")
                try:
                    # in client data data should be like {"MMT":0} in messages value should be 0 or 1
                    client_data = await asyncio.wait_for(websocket.recv(), timeout=3) # waiting for data(message) from websockets
                    print('client_data',client_data)

                    #  first keys from json file
                    get_key = list(json.loads(client_data).keys())[0]

                    # getting key name

                    plc_coil_reg = plc_json_data["outputs"][get_key]

                    # using key getting value here
                    plc_coil_reg_val=json.loads(client_data)[get_key]
                    try:
                        if get_key == "MMF" and plc_coil_reg_val == 1 :
                            print('before mmf write',datetime.now().isoformat())
                            try:
                                mmf_coil_write= await client.write_coil(1280, plc_coil_reg_val, slave=0x01)
                                mmf_coil_write= await client.write_coil(1281, 0, slave=0x01)
                            except Exception as e:
                                print("changes done in MMF write",e)
                            print('after mmf write', datetime.now().isoformat())
                        elif get_key == "MMR" and plc_coil_reg_val == 1:
                            try:
                                mmr_coil_write = await client.write_coil(1281, plc_coil_reg_val, slave=0x01)
                                mmr_coil_write = await client.write_coil(1280, 0, slave=0x01)
                            except Exception as e:
                                print("changes done in MMR ",e)
                        else:
                            print('...b....', get_key, datetime.now().isoformat())
                            try:
                                out_write = await client.write_coil(plc_coil_reg, plc_coil_reg_val, slave=0x01)
                            except Exception as e:
                                print("Exception in manual any other key changes",e)
                            print('...b....', datetime.now().isoformat())
                            print('out_write', out_write)
                    except Exception as e:
                        print("except mmf mmr ",e)

                    # try:
                    #     print('...b....',get_key, datetime.now().isoformat())
                    #     out_write = await client.write_coil(plc_coil_reg, plc_coil_reg_val, slave=0x01)
                    #     print('...b....', datetime.now().isoformat())
                    #     print('out_write',out_write)
                    # except Exception as e :
                    #     print('e screen 2',e)


                except asyncio.TimeoutError:
                    print("in except")
                    # No data received from the client within the timeout period
        except websockets.exceptions.ConnectionClosed:  # disconnect line
            print("Client disconnected screen 2")

    elif query_params['screen'][0] == "Settings":
        sending_data = get_interlock_json_data()
        await websocket.send(json.dumps(sending_data))

        try:
            settings_msg = await asyncio.wait_for(websocket.recv(), timeout=3)
            print('settings_msg', settings_msg)
            await on_receive(settings_msg)
            sending_data_u = get_interlock_json_data()
            await websocket.send(json.dumps(sending_data_u))
        except Exception as e:
            print('e in settings', e)

    elif query_params['screen'][0] == "Operations":
        try:
            operation_cycle_start = await asyncio.wait_for(websocket.recv(), timeout=3)
            await on_receive(operation_cycle_start)

            json_data = get_interlock_json_data()
            if json_data.get("Cycle_status") == "On":
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
                print('messagetask',message_task)

                while time.time() < end_time:

                    print("in while", datetime.now().isoformat())

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
                    json_data1 = get_interlock_json_data()  # Refresh JSON data
                    if json_data1.get("Cycle_status") == "Off":
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
                

                print('outof the loop 22')
                # Cancel the message handling task
                message_task.cancel()
                try:
                    await message_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            print('e operation', e)


    else:
        pass




async def main():
    # Enable tracemalloc
    tracemalloc.start()

    # Run the Modbus client
    await run_modbus_client()

    # Start the WebSocket server
    server = await websockets.serve(Screens_websocket_main, "192.168.29.144", 8765)

    # Run the WebSocket server until the application is terminated
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())





