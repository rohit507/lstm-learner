# This preprocessor takes in a CASAS data file and produces feature vectors and
# label vectors. Each feature vector is a snapshot of all the motion/door sensors
# at time t, and the label vector is a snapshot of all the lights at time t.
# For example, each timestamp in the original file will correspond to something
# like [0, 1, 0, 0, 1] => [0, 1], where two of the motion/door sensors have
# detected something and one of the lights is on.
# After assembling the complete state vectors for each timestep by holding
# values constant until a new update changes them, this preprocessor also trims
# the beginning of the dataset so that the final data only starts when all label
# devices have been seen. This is so that the learner is not training on
# unknown/incorrect labels.

import numpy as np
from copy import copy
import datetime
from time import time

filename = "../data/twor2010"
#filename = "../data/simple"
desired_input_types = ['M', 'D', 'L'] # events from motion, door, and light sensors will be used in feature vector
desired_label_types = ['L'] #predicting the next light event
features_save_filename = "features.npy"
labels_save_filename = "labels.npy"

desired_events = {'M': ['OFF', 'ON'],
                  'D': ['CLOSE', 'OPEN'],
                  'L': ['OFF', 'ON'], #not interested in events like DIM:183 from L007
                  'A': ['START', 'END']}

indent = "    "

def main():
    # get data and metadata
    print("loading data...")
    data, input_device_buckets, label_device_buckets, first_timestamps = load_data(filename)
    # build the input/label vectors and keep track of timestamps
    print("building vectors...")
    input_vectors, label_vectors, timestamps = build_vectors(data, input_device_buckets, label_device_buckets)
    # align data
    # HERE
    # use timestamps to remove vectors that occur before we've heard from all label devices at least once
    print("trimming vectors...")
    start_time = get_time_all_devices_seen(first_timestamps, desired_label_types)
    start_index = timestamps.index(start_time)
    input_vectors = input_vectors[start_index-1:-1] #off-by-one to align the events with the following light action
    label_vectors = label_vectors[start_index:]
    # save trimmed vectors
    print("saving vectors...")
    save_vectors(input_vectors, features_save_filename)
    save_vectors(label_vectors, labels_save_filename)
    print("saved vectors to " + features_save_filename + " and " + labels_save_filename)

def load_data(filename):
    with open(filename) as f:
        data = f.read().splitlines()
    # get list of all devices in dataset sorted into buckets by type
    device_buckets, first_timestamps = get_devices(data)
    # split into input and output devices
    input_device_buckets, label_device_buckets = filter_devices(device_buckets)
    return data, input_device_buckets, label_device_buckets, first_timestamps

def build_vectors(data, input_device_buckets, label_device_buckets):
    # initialize progress tracker
    num_samples = len(data)
    samples_processed = 0
    update_chunk = 200000 #samples
    start_time = time()
    start_chunk_time = start_time
    # initialize input and label vectors
    input_vectors = []
    label_vectors = []
    timestamps = []
    input_vector, input_event_indices = initialize_vector(input_device_buckets)
    label_vector, label_event_indices = initialize_vector(label_device_buckets)
    # for each timestep, update either input vector or label vector or neither (if a device type we're ignoring)
    for line in data:
        input_vector = zero_vector(len(input_vector))
        label_vector = zero_vector(len(label_vector))
        if is_well_formed(line):
            device = get_device(line)
            value = get_value(line)
            event = get_event(device, value)
            timestamp = get_timestamp(line) ############# AHHHHHHHHHH
            device_type = get_device_type(device)
            if device_type in desired_input_types or device_type in desired_label_types:
                try:
                    if device_type in desired_input_types:
                        input_vector[input_event_indices[event]] = 1
                    if device_type in desired_label_types:
                        label_vector[label_event_indices[event]] = 1
                    input_vectors.append(copy(input_vector))
                    label_vectors.append(copy(label_vector))
                    timestamps.append(timestamp)
                except KeyError:
                    pass #if it's a weird value (aka not ON/OFF OPEN/CLOSE, etc.), skip
                #print(input_vector),
                #print(label_vector)
        samples_processed += 1
        if samples_processed % update_chunk == 0:
            elapsed_minutes = round((time() - start_chunk_time)/60.0, 2)
            remaining_samples = num_samples - samples_processed
            remaining_chunks = remaining_samples / update_chunk
            remaining_minutes = round(remaining_chunks * elapsed_minutes, 2)
            print(indent + "processed " + str(samples_processed) + " out of " + str(num_samples))
            print(indent + str(elapsed_minutes) + " minutes elapsed since last update, " + str(remaining_minutes) + " estimated minutes remaining")
            start_chunk_time = time()
    total_minutes = round((time() - start_time)/60.0, 2)
    print(indent + "total elapsed time: " + str(total_minutes) + " minutes")
    return input_vectors, label_vectors, timestamps

def get_time_all_devices_seen(first_timestamps, desired_types):
    # get first occurrences of label devices
    first_device_timestamps = filter_timestamps_by_device_type(first_timestamps, desired_types)
    # find the last first occurrence
    all_devices_seen_timestamp = get_last_timestamp(first_device_timestamps)
    return all_devices_seen_timestamp

def save_vectors(vectors, filename):
    # build numpy matrices
    num_samples = len(vectors)
    num_features = len(vectors[0]) # semantically, num_outputs for the label vector
    matrix = np.zeros((num_samples, num_features))
    # add the content
    for i in range(num_samples):
        for j in range(num_features):
            try:
                matrix[i][j] = vectors[i][j]
            except ValueError:
                print("ERROR:"),
                print(vectors[i])
    # write to file
    print(matrix)
    matrix.dump(open(filename, "wb"))

def filter_timestamps_by_device_type(timestamp_buckets, desired_types):
    timestamps = []
    for device in timestamp_buckets:
        if get_device_type(device) in desired_types:
            timestamps.append(timestamp_buckets[device])
    return timestamps

def get_last_timestamp(timestamps):
    timestamps.sort()
    #print(timestamps)
    return timestamps[-1]

# returns list of devices sorted into buckets by type
# eg, {'M': ['M001', 'M002'],
#      'D': ['D001']}
def get_devices(data):
    device_type_buckets = {}
    device_first_occurrences = {}
    for line in data:
        if is_well_formed(line):
            device = get_device(line)
            device_type = get_device_type(device)
            if device_type not in device_type_buckets:
                device_type_buckets[device_type] = [device]
                device_first_occurrences[device] = get_timestamp(line)
            else:
                if device not in device_type_buckets[device_type]:
                    device_type_buckets[device_type].append(device)
                    device_first_occurrences[device] = get_timestamp(line)
    return device_type_buckets, device_first_occurrences

def filter_devices(device_buckets):
    input_device_buckets = {}
    label_device_buckets = {}
    for device_type in device_buckets:
        if device_type in desired_input_types:
            input_device_buckets[device_type] = device_buckets[device_type]
        if device_type in desired_label_types:
            label_device_buckets[device_type] = device_buckets[device_type]
    return input_device_buckets, label_device_buckets

def is_well_formed(line):
    fields = line.split()
    return (len(fields) >= 4)

def get_device(line):
    return line.split()[2]

def get_device_type(device):
    return device[0]

def get_value(line):
    return line.split()[3]

def get_activity(line):
    return line.split()[4]

def get_event(device, value):
    return str(device) + '_' + str(value)

def encode(value):
    try:
        encoded_value = encoding[value]
    except KeyError:
        encoded_value = float(value) # This can throw value error
    return encoded_value

def initialize_vector(device_buckets):
    # figure out how many features the input vector will have
    # devices and their possible event values according to type
    # e.g., <m1_OFF, m1_ON, d1_CLOSED, d1_OPEN...>
    # can't just record all the events we see, because we're not interested in
    # all devices (don't care about P001) and we're not interest in all events
    # (don't care about DIM:183 from L007, just ON/OFF).
    feature_count = 0
    event_indices = {}
    for device_type in device_buckets:
        for device in device_buckets[device_type]:
            for value in desired_events[device_type]:
                event = get_event(device, value)
                event_indices[event] = feature_count
                feature_count += 1

    # create a default vector
    initial_vector = zero_vector(feature_count)

    print(event_indices)

    # return the default vector with the correct number of features
    # and the mapping from each device to its index in the feature vector
    return initial_vector, event_indices

def zero_vector(length):
    vector = []
    for i in range(length):
        vector.append(0)
    return vector

def get_timestamp(line):
    fields = line.split()
    timestamp_str = fields[0] + ' ' + fields[1]
    try:
        timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").timestamp()
    except ValueError:
        timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S").timestamp()
    return timestamp

main()
