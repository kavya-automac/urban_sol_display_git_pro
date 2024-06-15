import json
import logging
import asyncio
import websocket
import websockets
import datetime
from urllib.parse import parse_qs, urlparse
from pymodbus.client import AsyncModbusSerialClient
import time
from datetime import datetime
import logging
from logging.handlers import TimedRotatingFileHandler
import os


todays_date=datetime.now().date()
print('todays_date',todays_date)
# current_script_path = os.path.realpath(__file__)
current_script_path = os.path.abspath(__file__)
print('current_script_path',current_script_path)

Base_dir = os.path.dirname(current_script_path)
print(f"Current script directory: {Base_dir}")

log_directory = os.path.join(Base_dir, 'logs')
log_filename = 'application_' + str(todays_date) + '.log'
log_file_path = os.path.join(log_directory, log_filename)
print('log_file_path:', log_file_path)

# Ensure the log directory exists
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# Create a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create a handler that writes log messages to a file, with a new file created every day and files older than 7 days deleted
handler = TimedRotatingFileHandler(log_file_path, when='midnight', interval=1, backupCount=7)
handler.setLevel(logging.DEBUG)

# Create a formatter and set it for the handler
formatter = logging.Formatter('%(asctime)s - %(funcName)s- %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(handler)
logging.basicConfig(level=logging.INFO)


async def run_modbus_client():
    try:
        global client
        client = AsyncModbusSerialClient(method='rtu', port="COM7", baudrate=9600, parity='E', stopbits=1)
        # client = ModbusClient.ModbusSerialClient(type='rtu', port='COM6', parity='E', baudrate=9600, stopbits=1, bytesize=8)
        con = await client.connect()
        logger.info("In modbus try %s",con)
        print("connectedd", con)
    except Exception as e:
        logger.error(" connection error %s",e)

plc_json_file_path = Base_dir+'/plc_registers_addresses.json'


def plc_address_load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data


interlock_json_file_path =  Base_dir+'/interlocks.json'


def interlock_load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

# getting plc addresses


plc_json_data = plc_address_load_json(plc_json_file_path)

# all paramters data loads here


async def get_interlock_json_data():
    return interlock_load_json(interlock_json_file_path)

def interlock_save_json(file_path, data):
    with open(file_path, 'w') as file:
        json.dump(data, file, indent=4)

# any changes occurs in interlocks it will update in json file

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
    logger.info("motor rev before writing into plc %s", datetime.now().isoformat())
    try:
        await client.write_coils(1280, [0,1], slave=0x01)
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))
    except  Exception as e:

        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message":str(type(e).__name__),
                                         "Time_stamp":datetime.now().isoformat(" ").split(".")[0]}))
        logger.error("motor rev failed to write into plc  %s", e)

    logger.info("motor rev after writing  %s", datetime.now().isoformat())
    global pause_duration
    logger.info("motor running in reverese  - > %s", datetime.now().isoformat())
    for _ in range(motor_rev_time):

        if time.time() >= end_time:
            logger.info("stopping motor rev due to end time %s", datetime.now().isoformat())
            break
        json_data = await get_interlock_json_data()
        if json_data.get("Cycle_status") == "Off":
            logger.info("motor rev stopped due to cycle off %s", datetime.now().isoformat())
            break

        if interlocks_should_pause(json_data):
            pause_start = time.time()
            logger.info("motor rev paused due to interlock %s", datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = await get_interlock_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            logger.info("Resuming motor reverse %s", datetime.now().isoformat())
        await asyncio.sleep(1)
    logger.info("Motor rev completed %s", datetime.now().isoformat())


async def wait_period(wait_time, end_time,websocket):
    logger.info("wait_period before writing into plc%s", datetime.now().isoformat())
    try:
        await client.write_coils(1280, [0,0], slave=0x01)
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))

    except Exception as e:
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
                                         "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
                                         }))
        logger.error("failed to write into plc (wait period)%s", datetime.now().isoformat())
    logger.info("wait_period After writing into plc %s", datetime.now().isoformat())
    global pause_duration
    logger.info("wait_period After writing into plc %s", datetime.now().isoformat())


    logger.info("waiting until wait time %s", datetime.now().isoformat())
    for _ in range(wait_time):

        if time.time() >= end_time:
            logger.info("Stopping wait_period due to end time %s", datetime.now().isoformat())
            break
        json_data = await get_interlock_json_data()
        if json_data.get("Cycle_status") == "Off":
            logger.info("Stopping wait_period due to cycle status off %s", datetime.now().isoformat())
            break
        if interlocks_should_pause(json_data):
            pause_start = time.time()
            logger.info("Pausing  wait_period due to  interlock %s", datetime.now().isoformat())
            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = await get_interlock_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            logger.info("Resuming  wait_period  %s", datetime.now().isoformat())
        await asyncio.sleep(1)
    logger.info("Wait complete  %s", datetime.now().isoformat())


async def blower_off(delay,websocket):
    logger.info("Blower before On  %s", datetime.now().isoformat())

    await asyncio.sleep(delay)
    try:

        await client.write_coil(1282, 0, slave=0x01)
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))
    except Exception as e:
        # pop_ups = True
        # await websocket.send(json.dumps({"Pop_up": pop_ups, "message":str(type(e).__name__)}))
        logger.error("Blower failed to write into plc   %s", e)

    logger.error("Blower off  %s", datetime.now().isoformat())


async def motor_fwd(end_time,websocket):
    logger.info("motor forward writing into plc %s", datetime.now().isoformat())

    try:

        await client.write_coils(1280, [1,0,1], slave=0x01)
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))
    except Exception as e:
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
                                         "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
                                         }))
        logger.error("motor forward failed to write into plc %s",e)

    asyncio.create_task(blower_off(blower_time,websocket))

    logger.info("motor forward  after writing into plc %s", datetime.now().isoformat())
    global pause_duration
    logger.info("motor forward running %s", datetime.now().isoformat())

    for _ in range(motor_fwd_time):

        if time.time() >= end_time:
            logger.info(" Stopping motor forward due to end time %s", datetime.now().isoformat())

            break
        json_data = await get_interlock_json_data()
        if json_data.get("Cycle_status") == "Off":
            logger.info("motor forward stopped due to cycle off %s", datetime.now().isoformat())

            break

        if interlocks_should_pause(json_data):
            pause_start = time.time()
            logger.info("Pausing motor forward due to interlock %s", datetime.now().isoformat())

            while interlocks_should_pause(json_data):
                await asyncio.sleep(1)
                json_data = await get_interlock_json_data()
            pause_end = time.time()
            pause_duration += (pause_end - pause_start)
            logger.info("Resuming motor forward  %s", datetime.now().isoformat())

        await asyncio.sleep(1)
    logger.info("motor forward  completed %s", datetime.now().isoformat())


async def all_parameters_off():
    try:
        await client.write_coils(1280, [0, 0, 0,0,0], slave=0x01)
    except Exception as e:
        logger.error("failed to off all parameters %s", e)






async def on_receive(message):
    try:
        logger.info("Received message from websocket %s", message)

        settings_msg_data = json.loads(message)
        await interlock_update_json_data(settings_msg_data)
    except Exception as e:
        logger.error("Error processing message from websocket %s", e)


async def handle_messages(websocket):
    logger.info("handler message from websocket ")

    async for message in websocket:
        logger.info("handler message from websocket %s", message)

        await on_receive(message)







async def get_inputs(websocket):

    input_data = plc_json_data["inputs"]
    ip_dict = {}
    try:

        for k, v in input_data.items():

            inputs = await client.read_discrete_inputs(v, 1, slave=0x01)

            ip_dict[k] = inputs.bits[0]
        logger.info("input result data")

        pop_ups = False
        ip_dict.update({"Pop_up": pop_ups})
        # await websocket.send(
        #     json.dumps({"Pop_up": pop_ups}))

        return ip_dict
    except Exception as e:
        pop_ups = True
        # await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
        #                                  "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
        #                                  }))
        logger.info("input result data failed to load %s ",e)
        print("input exception",e)
        return {{"Pop_up": pop_ups, "message": str(type(e).__name__),
                                         "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
                                         }}

        # return {
        #     "MMtrip": False,
        #     "BMT": False,
        #     "DoorOpen": False,
        #     "SppOk": False,
        #     "Eswitch": True
        # }

# reading ouput addresses data

async def get_output(websocket):

    output_data = plc_json_data["outputs"]
    # print('..',output_data)
    op_dict = {}

    try:

        for k,v in output_data.items():
            outputs = await client.read_coils(v, 1, slave=0x01)
            op_dict[k] = outputs.bits[0]
        logger.info("output result data ")
        pop_ups = False
        op_dict.update({"Pop_up": pop_ups})
        # await websocket.send(
        #     json.dumps({"Pop_up": pop_ups}))

        return op_dict
    except Exception as e:
        logger.info("output result data failed to load %s ", e)
        pop_ups = True
        # await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
        #                                  "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
        #                                  }))

        return {{"Pop_up": pop_ups, "message": str(type(e).__name__),
                                         "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
                                         }}
        # return {
        #     "MMF": True,
        #     "MMR": False,
        #     "Blower_Motor": True,
        #     "Heater": False,
        #     "Acr": False
        # }



async def IO_screen(websocket):
    logger.info(" ioscreen  connected ")
    try:
        pop_ups = False
        await websocket.send(
            json.dumps({"Pop_up": pop_ups}))
        while True:
            ip_data = await get_inputs(websocket)
            op_data = await get_output(websocket)
            Data = {**ip_data, **op_data}  # merege 2 dicts
            logger.info("merge 2 dicts ")
            await websocket.send(json.dumps(Data))

            # Wait for one second before sending the next message
            await asyncio.sleep(1)
    except Exception as e:  # disconnect line
        pop_ups = True
        await websocket.send(
            json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
                        "Time_stamp":datetime.now().isoformat(" ").split(".")[0]}))
        logger.error(" Io Screen Client disconnected")

async def Manual_screen(websocket):
    logger.info("Manual screen connected ")
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
                logger.info("Manual screen client data (message body) %s",client_data)

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
                        logger.info("Before MMF write into plc %s ",datetime.now().isoformat())
                        try:

                            mmf_coil_write = await client.write_coil(1280, plc_coil_reg_val, slave=0x01)
                            mmf_coil_write = await client.write_coil(1281, 0, slave=0x01)
                            pop_ups = False
                            await websocket.send(json.dumps({"Pop_up": pop_ups}))
                        except Exception as e:

                            pop_ups = True
                            await websocket.send(
                                json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
                                            "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
                                            }))
                            logger.error("failed to write MFF data into plc %s ", e)

                        logger.info("after  MMF write into plc %s ",datetime.now().isoformat())
                    elif get_key == "MMR" and plc_coil_reg_val == 1:
                        logger.info("Before MMR write into plc %s ",datetime.now().isoformat())

                        try:

                            mmr_coil_write = await client.write_coil(1281, plc_coil_reg_val, slave=0x01)
                            mmr_coil_write = await client.write_coil(1280, 0, slave=0x01)
                            pop_ups = False
                            await websocket.send(json.dumps({"Pop_up": pop_ups}))
                        except Exception as e:
                            pop_ups = True
                            await websocket.send(
                                json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
                                            "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
                                            }))
                            logger.error("failed to write MMR data into plc %s ", e)


                    else:
                        logger.info("Except MMF MMR  writing diff paramters data into plc %s ", datetime.now().isoformat())

                        try:

                            out_write = await client.write_coil(plc_coil_reg, plc_coil_reg_val, slave=0x01)
                            pop_ups = False
                            await websocket.send(json.dumps({"Pop_up": pop_ups}))
                        except Exception as e:
                            pop_ups = True
                            await websocket.send(
                                json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
                                            "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
                                            }))
                            logger.error("Failed to write diff paramters data into plc %s ",e)


                        logger.info("after writing other parameters %s ", datetime.now().isoformat())

                except Exception as e:
                    pop_ups = True
                    await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
                                                     "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
                                                     }))

                    print("except mmf mmr ", e)
                    logger.error("failed to write paramters data into plc %s ", e)

            except Exception as e:
                logger.error("no data got from websocket msg body %s ",e)

    except Exception as e :  # disconnect line
        pop_ups = True
        await websocket.send(json.dumps({"Pop_up": pop_ups, "message": str(type(e).__name__),
                                         "Time_stamp": datetime.now().isoformat(" ").split(".")[0]
                                         }))
        logger.error(" Manual screen disconnected", e)



async def Settings_screen(websocket):
    logger.info(" Settings Screen Connected ")

    sending_data = await get_interlock_json_data()
    await websocket.send(json.dumps(sending_data))
    # print(await asyncio.wait_for(websocket.recv(), timeout=3))

    try:
        print("sssstry")

        settings_msg = await asyncio.wait_for(websocket.recv(), timeout=3)
        logger.info(" Changes done ,got from websocket %s",settings_msg)
        await on_receive(settings_msg)
        sending_data_u = await get_interlock_json_data()
        await websocket.send(json.dumps(sending_data_u))
        pop_ups = False
        await websocket.send(json.dumps({"Pop_up": pop_ups}))

    except Exception as e:
        # pop_ups = True
        # await websocket.send(json.dumps({"Pop_up": pop_ups, "message":str(type(e).__name__)}))
        logger.error(" Settings Screen Exception %s",e)
        print('e in settings', e)

async def Operations_screen(websocket):
    logger.info("Operations Screen Connected ")

    json_data = await get_interlock_json_data()
    print("json_data", json_data)
    await websocket.send(json.dumps({"Cycle_status": json_data["Cycle_status"]}))
    try:

        operation_cycle_start = await asyncio.wait_for(websocket.recv(), timeout=10)

        print('operation_cycle_start',operation_cycle_start)
        logger.info("Cycle status form message body %s ", operation_cycle_start)

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
            logger.info("Start Time (ISO 8601 format) %s ", start_iso)
            logger.info("End Time (ISO 8601 format)) %s ", end_iso)

            print("Start Time (ISO 8601 format):", start_iso)
            print("End Time (ISO 8601 format):", end_iso)

            # Start the message handling task
            message_task = asyncio.create_task(handle_messages(websocket))


            while time.time() < end_time:
                logger.info("cycle starts, in while %s", datetime.now().isoformat())


                await motor_fwd(end_time,websocket)
                await wait_period(wait_time_fwd, end_time,websocket)
                await motor_rev(end_time,websocket)
                await wait_period(wait_time_rev, end_time,websocket)

                cycle_count += 1

                if no_of_cycles == cycle_count:
                    await wait_period(cycle_wait_time, end_time,websocket)
                    cycle_count = 0

                if pause_duration > 0:
                    logger.info("Pause duration after updation %s", pause_duration)

                    print('pause_duration after updation', pause_duration)
                    end_time += pause_duration
                    pause_duration = 0  # Reset pause duration
                json_data1 = await get_interlock_json_data()  # Refresh JSON data
                if json_data1.get("Cycle_status") == "Off":
                    await websocket.send(json.dumps({"Cycle_status": json_data1["Cycle_status"]}))
                    await all_parameters_off()
                    logger.info("Cycle stop received, breaking out of the loop %s", datetime.now().isoformat())

                    print('Cycle stop received, breaking out of the loop')

                    break

                if time.time() >= end_time:
                    logger.info("Cycle end time reached %s'", end_iso)
                    logger.info("Ending process at: %s'", datetime.now().isoformat())

                    print("Cycle end time reached:", end_iso)
                    print("Ending process at:", datetime.now().isoformat())
                    await all_parameters_off()
                    # await client.write_coil(1282, 0, slave=0x01)

                    break

            pop_ups = False
            await websocket.send(json.dumps({"Pop_up": pop_ups}))

            print('outof the loop 22')
            logger.info("outof the loop 22 %s", datetime.now().isoformat())

            # Cancel the message handling task
            message_task.cancel()
            try:
                await message_task
            except asyncio.CancelledError:
                pass
    except Exception as e:
        # pop_ups=True
        # await websocket.send(json.dumps({"Pop_up":pop_ups,"message":str(type(e).__name__)}))
        logger.info("Exception in operations screen %s", e)

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
        logger.error(f"Connection closed: {e.code} - {e.reason}")
    except websockets.InvalidMessage as e:
        logger.error(f"Invalid message received: {e}")
    except websockets.WebSocketTimeout as e:
        logger.error(f"WebSocket operation timed out: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


async def main():
    try:
        async with websockets.serve(echo, "192.168.29.144", 8765):
            logger.info("WebSocket server started on ws://192.168.29.144:8765")
            client = None
            print("client in main...", client)
            logger.error(f'client{client}')
            client = await run_modbus_client()




            await asyncio.Future()  # run forever
    except websockets.WebSocketException as e:
        logger.error(f"WebSocket server error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during server start: {e}")


if __name__ == "__main__":
    asyncio.run(main())




