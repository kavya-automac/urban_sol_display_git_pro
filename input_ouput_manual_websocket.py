import asyncio
import json
import random

import websockets
import datetime
from urllib.parse import parse_qs, urlparse
import pymodbus.client.serial as ModbusClient

json_file_path = 'plc_registers_addresses.json'

# Function to load JSON data from a file
def load_json(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

# Load the JSON data
json_data = load_json(json_file_path)
# print('json_data',json_data)


#modbus rtu connection
try:
    client = ModbusClient.ModbusSerialClient(type='rtu',port='COM6',parity='E',baudrate=9600, stopbits=1, bytesize=8)
    con = client.connect()
    print("connectedd",con)
except Exception as e:
    print("e",e)



def get_inputs():

    input_data = json_data["inputs"]
    ip_dict = {}
    try:
        for k, v in input_data.items():

            inputs = client.read_discrete_inputs(v, 1, slave=0x01)
            # print('inputs',inputs,k,v)
            # print('inputs bits',inputs.bits)
            ip_dict[k] = inputs.bits[0]
        print('input result', ip_dict)

        return ip_dict
    except:
        return {
            "MMtrip": False,
            "BMT": False,
            "DoorOpen": False,
            "SppOk": False,
            "Eswitch": True
        }

def get_output():
    # json_data = load_json(json_file_path)
    output_data=json_data["outputs"]
    op_dict={}
    try:
        for k,v in output_data.items():
            outputs = client.read_coils(v, 1, slave=0x01)
            op_dict[k] = outputs.bits[0]
        print('op_result',op_dict)

        return op_dict
    except:
        return {
            "MMF": True,
            "MMR": False,
            "Blower_Motor": True,
            "Heater": False,
            "Acr": False
        }


async def send_data(websocket, path):
    # Parse query parameters from the path

    query_params = parse_qs(urlparse(path).query)
    # print('query_params',query_params)
    # print('query_params type',type(query_params))

    # print('query_params',query_params['machine_id'][0])

    if query_params['screen'][0]=="screen1":
        try:
            while True:
                ip_data=get_inputs()
                op_data=get_output()
                Data = {**ip_data, **op_data} #merege 2 dicts
                # print('data',Data)
                await websocket.send(json.dumps(Data))

                # Wait for one second before sending the next message
                await asyncio.sleep(1)
        except websockets.exceptions.ConnectionClosed:  # disconnect line
            print("Client disconnected")

    elif query_params['screen'][0]=="Manual":

        try:
            while True:
                screen2_op_data=get_output() # only outputs
                await websocket.send(json.dumps(screen2_op_data))
                # print("after sending")
                try:
                    # in client data data should be like {"MMT":0} in messages value should be 0 or 1
                    client_data = await asyncio.wait_for(websocket.recv(), timeout=3) # waiting for data(message) from websockets
                    print('client_data',client_data)

                    #  first keys from json file
                    get_key=list(json.loads(client_data).keys())[0]



                    # getting key name
                    plc_coil_reg = json_data["outputs"][get_key]

                    # using key getting value here
                    plc_coil_reg_val=json.loads(client_data)[get_key]
                    try:
                        if get_key == "MMF" and plc_coil_reg_val == 1 :
                            mmf_coil_write= client.write_coil(1280, plc_coil_reg_val, slave=0x01)
                            mmf_coil_write= client.write_coil(1281, 0, slave=0x01)
                        elif get_key == "MMR" and plc_coil_reg_val == 1:
                            mmf_coil_write = client.write_coil(1281, plc_coil_reg_val, slave=0x01)
                            mmf_coil_write = client.write_coil(1280, 0, slave=0x01)
                    except Exception as e:
                        print("except mmf mmr ",e)

                    # print('plc_coil_reg_val',plc_coil_reg_val)
                    # out_write = client.write_coil(1283,0, slave=0x01)

                    try:
                        out_write = client.write_coil(plc_coil_reg, plc_coil_reg_val, slave=0x01)
                        print('out_write',out_write)
                    except Exception as e :
                        print('e screen 2',e)


                except asyncio.TimeoutError:
                    print("in except")
                    # No data received from the client within the timeout period
                    pass

        except websockets.exceptions.ConnectionClosed:  # disconnect line
            print("Client disconnected screen 2")
    else:
        pass


if __name__ == "__main__":
    server = websockets.serve(send_data, "192.168.29.144", 8765)
    print('server',server)

    asyncio.get_event_loop().run_until_complete(server)
    asyncio.get_event_loop().run_forever()

