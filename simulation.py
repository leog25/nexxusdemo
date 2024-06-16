import os
import sys
import traci
import math
import random
import keyboard
from flask_socketio import SocketIO, emit

contract_counter = 0
vehicle_data = {'contracts': [], 'vehicles': [], 'edges': [], 'bounds': {}}
socketio = None  # Placeholder for the socketio instance

def calculate_distance(pos1, pos2):
    """Calculate the Euclidean distance between two positions."""
    return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

class DAOContract:
    def __init__(self, timestamp, initiator_id, initiator_position):
        global contract_counter
        self.contract_id = contract_counter
        contract_counter += 1
        self.timestamp = timestamp
        self.initiator_id = initiator_id
        self.initiator_position = initiator_position
        self.participants = {initiator_id: initiator_position}  # Automatically add initiator

    def add_participant(self, vehicle_id, position):
        if vehicle_id != self.initiator_id and calculate_distance(self.initiator_position, position) <= 5:
            self.participants[vehicle_id] = position

def get_contract_data(contracts):
    return [{'contract_id': contract.contract_id,
             'timestamp': contract.timestamp,
             'initiator_id': contract.initiator_id,
             'participants': contract.participants} for contract in contracts]

def get_vehicle_data():
    vehicles = []
    for vehicle_id in traci.vehicle.getIDList():
        position = traci.vehicle.getPosition(vehicle_id)
        vehicles.append({
            'id': vehicle_id,
            'x': position[0],
            'y': position[1],
            'speed': traci.vehicle.getSpeed(vehicle_id)
        })
    return vehicles

def get_edge_data():
    edges = traci.edge.getIDList()
    edge_data = []
    for edge in edges:
        lanes = traci.edge.getLaneNumber(edge)
        for lane_index in range(lanes):
            shape = traci.lane.getShape(f"{edge}_{lane_index}")
            edge_data.append({
                'id': f"{edge}_{lane_index}",
                'shape': shape
            })
    return edge_data

def get_network_bounds():
    edges = traci.edge.getIDList()
    min_x = float('inf')
    min_y = float('inf')
    max_x = float('-inf')
    max_y = float('-inf')
    for edge in edges:
        lanes = traci.edge.getLaneNumber(edge)
        for lane_index in range(lanes):
            shape = traci.lane.getShape(f"{edge}_{lane_index}")
            for (x, y) in shape:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    return {'min_x': min_x, 'min_y': min_y, 'max_x': max_x, 'max_y': max_y}

class Vehicle:
    def __init__(self, vehicle_id):
        self.vehicle_id = vehicle_id
        self.locational_data = []
        self.contracts = []

    def update_location(self, timestamp, position):
        self.locational_data.append((timestamp, position))

    def initiate_contract(self, timestamp):
        if not self.locational_data:
            return None
        current_position = self.locational_data[-1][1]
        contract = DAOContract(timestamp, self.vehicle_id, current_position)
        self.contracts.append(contract)
        return contract

    def participate_in_contract(self, contract):
        if self.locational_data:
            timestamp, position = self.locational_data[-1]
            contract.add_participant(self.vehicle_id, position)

def get_random_edge():
    edges = traci.edge.getIDList()
    return random.choice(edges)

def add_vehicle(vehicles):
    vehicle_id = f"manual_{len(vehicles)}"
    vehicles[vehicle_id] = Vehicle(vehicle_id)
    
    while True:
        start_edge = get_random_edge()
        end_edge = get_random_edge()
        
        route = traci.simulation.findRoute(start_edge, end_edge)
        if route.edges:
            break
    
    route_id = f"route_{vehicle_id}"
    traci.route.add(route_id, route.edges)
    traci.vehicle.add(vehicle_id, routeID=route_id)
    traci.vehicle.setColor(vehicle_id, (255, 0, 0))  # Set the vehicle color to red
    print(f"Added vehicle {vehicle_id} with route from {start_edge} to {end_edge}")

def update_vehicle_targets(vehicles):
    for vehicle_id in vehicles:
        current_edge = traci.vehicle.getRoadID(vehicle_id)
        if current_edge == traci.vehicle.getRoute(vehicle_id)[-1]:  # If the vehicle reached its target
            while True:
                new_target = get_random_edge()
                route = traci.simulation.findRoute(current_edge, new_target)
                if route.edges:
                    traci.vehicle.setRoute(vehicle_id, route.edges)
                    print(f"Updated route for vehicle {vehicle_id} to new target {new_target}")
                    break

def run_simulation(socketio_instance):
    global socketio
    socketio = socketio_instance

    if 'SUMO_HOME' in os.environ:
        tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
        sys.path.append(tools)
    else:
        sys.exit("Please declare the environment variable 'SUMO_HOME'")

    sumoBinary = "sumo-gui"
    sumoCmd = [sumoBinary, "-c", "grid.sumocfg"]

    traci.start(sumoCmd)
    vehicles = {}
    contracts = []
    contract_interval = 1
    next_contract_time = 0
    network_bounds = get_network_bounds()

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            current_time = traci.simulation.getTime()

            if current_time >= next_contract_time:
                next_contract_time += contract_interval

                vehicle_ids = traci.vehicle.getIDList()
                for vehicle_id in vehicle_ids:
                    if vehicle_id not in vehicles:
                        vehicles[vehicle_id] = Vehicle(vehicle_id)
                    position = traci.vehicle.getPosition(vehicle_id)
                    vehicles[vehicle_id].update_location(current_time, position)

                for vehicle_id, vehicle in vehicles.items():
                    contract = vehicle.initiate_contract(current_time)
                    if contract:
                        for vid, v in vehicles.items():
                            v.participate_in_contract(contract)

                        if len(contract.participants) > 1:  # Change here to check for more than 1 participant
                            contracts.append(contract)
            
            # Remove expired contracts (example logic, adjust as necessary)
            contracts = [contract for contract in contracts if traci.simulation.getTime() - contract.timestamp < 10]
            
            # Check for the 'T' key press to add a vehicle
            if keyboard.is_pressed('T'):
                add_vehicle(vehicles)
                print(f"Vehicle manually added at time {current_time}")
            
            # Update vehicle targets to keep them within the network
            update_vehicle_targets(vehicles)
            
            # Update contract and vehicle data for real-time display
            vehicle_data['contracts'] = get_contract_data(contracts)
            vehicle_data['vehicles'] = get_vehicle_data()
            vehicle_data['edges'] = get_edge_data()
            vehicle_data['bounds'] = network_bounds
            socketio.emit('update', vehicle_data)

    finally:
        traci.close()
