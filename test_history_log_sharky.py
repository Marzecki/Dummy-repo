import struct
from datetime import datetime

import allure
import pytest
from time import sleep, time
from enum import Enum
from random import randint

from meter_interaction.com_interactions import send_command_return_response
from meter_interaction.itep_mock import ItepMock

from support.commands_usage import call_command_to_delete_log, is_locked_storage_operation, lock_storage_mode
from meter_interaction import com_interactions
from support.hydrus2.commands import send_command, set_volume_accus, trigger_function, disable_ultrasonic_simulation
from support.hydrus2.communication import close_irda_communication_window, CommunicationMode
from support.hydrus2.errors import CiFieldError
from support.meter_types import OperationMode, MeterOperation, MeterMode, TriggerFunction, UltrasonicSimulationMode
from support.data_parser import reverse_stream, int_to_lsb

# ***************************************************************************************
# lists and dictionaries
# ****************************************************************************************
HistoryLogDataSetSizes = {
    'dateTimeTypeG': 2,
    'dateTimeTypeF': 4,
    'sumVolume': 4,
    'forwardVolume': 4,
    'backwardVolume': 4,
    'currentFlow': 3,
    'maximumFlow': 3,
    'minimumFlow': 3,
    'mediumTemp': 2,
    'ambientTemp': 2,
    'operatingHours': 3,
    'errorHours': 2,
    'errorState': 4,
}


class HistoryLogDataSetBitPlaces(Enum):
    DATETIME_TYPE_G = 0x0100
    DATETIME_TYPE_F = 0x0200
    VOLUME_SUM = 0x0400
    VOLUME_FORWARD = 0x0800
    VOLUME_BACKWARD = 0x1000
    FLOW_CURRENT = 0x2000
    FLOW_MAXIMUM = 0x4000
    FLOW_MINIMUM = 0x8000
    TEMP_MEDIUM = 0x0001
    TEMP_AMBIENT = 0x0002
    OPERATING_HOURS = 0x0004
    ERROR_HOURS = 0x0008
    ERROR_STATE = 0x0010


HISTORY_LOG_DATA_SETS_AMOUNT = 14
HISTORY_LOG_DATA_SETS = [
    256,  # dateTimeTypeG
    512,  # dateTimeTypeF
    1024,  # sumVolume
    2048,  # forwardVolume
    4096,  # backwardVolume
    8192,  # currentFlow
    16384,  # maximumFlow
    32768,  # minimumFlow
    1,  # mediumTemp
    2,  # ambientTemp
    4,  # operatingHours
    8,  # errorHours
    16,  # errorState
    0xFF1F  # ALL
]

HISTORY_LOG_DATA_SELECTOR_AMOUNT_OF_SELECTS = 14
HISTORY_LOG_DATA_SELECTOR = {
    "dateTimeTypeG": 256,  # dateTimeTypeG
    "dateTimeTypeF": 512,  # dateTimeTypeF
    "sumVolume": 1024,  # sumVolume
    "forwardVolume": 2048,  # forwardVolume
    "backwardVolume": 4096,  # backwardVolume
    "currentFlow": 8192,  # currentFlow
    "maximumFlow:": 16384,  # maximumFlow
    "minimumFlow": 32768,  # minimumFlow
    "mediumTemp": 1,  # mediumTemp
    "ambientTemp": 2,  # ambientTemp
    "operatingHours": 4,  # operatingHours
    "errorHours": 8,  # errorHours
    "errorState": 16,  # errorState
    "ALL": 0xFF1F  # ALL
}

HARMONIZED_DM_ERRORS_AMOUNT = 15
HARMONIZED_DM_ERRORS = {
    "checksum": 1,
    "hardwareFlow": 2,
    "backflow": 32,
    "undersizedMeter": 1024,
    "noUsage": 4096,
    "measurementInterference": 128,
    "hardWareTemperature": 4,
    "highMediumTemperature": 16384,
    "freezingRisk": 8192,
    "lowBattery": 131072,
    "toMuchCommunication": 32768,
    "leakage": 8,  # errorHours
    "failSaveMode": 64,
    "metrologicalLogAccess": 65536,
    "airInPipe": 2048,
}

ERROR_HANDLER_ERROR_ID_AMOUNT = 17
ERROR_HANDLER_ERROR_ID = {
    "anyApplicationError": 1 << 0,
    "checksum": 1 << 1,
    "hardwareFlow": 1 << 2,
    "hardWareTemperature": 1 << 3,
    "leakage": 1 << 4,
    "undersizedMeter": 1 << 5,
    "backflow": 1 << 6,
    "failSaveMode": 1 << 7,
    "airInPipe": 1 << 8,
    "noUsage": 1 << 9,
    "measurementInterference": 1 << 10,
    "freezingRisk": 1 << 11,
    "highMediumTemperature": 1 << 12,
    "toMuchCommunication": 1 << 13,
    "metrologicalLogAccess": 1 << 14,
    "lowBattery": 1 << 15,
    "systemReset": 1 << 16,
}

HISTORY_LOG_INTERVALS_AMOUNT = 12
HISTORY_LOG_INTERVALS = [
    "0100",  # yearly
    "0200",  # monthly_middle
    "0300",  # monthly_end
    "0400",  # weekly_sunday
    "0500",  # weekly_monday
    "0600",  # weekly_tuesday
    "0700",  # weekly_wednesday
    "0800",  # weekly_thursday
    "0900",  # weekly_friday
    "0A00",  # weekly_saturday
    "0B00",  # daily
    "0C00",  # hourly
]

intervals_dict_time_alarms = {'yearly': '3B 17 BF 2C',  # 31.12.21 23:59
                              'monthly_middle': '3B 17 AF 2C',  # 15.12.21 23:59
                              'monthly_end': '3B 17 BF 2C',  # 31.12.21 23:59
                              'weekly_sunday': '3B 17 B3 2C',  # 19.12.21 23:59
                              'weekly_monday': '3B 17 B4 2C',  # 20.12.21 23:59
                              'weekly_tuesday': '3B 17 B5 2C',  # 21.12.21 23:59
                              'weekly_wednesday': '3B 17 AF 2C',  # 15.12.21 23:59
                              'weekly_thursday': '3B 17 B7 2C',  # 23.12.21 23:59
                              'weekly_friday': '3B 17 BF 2C',  # 31.12.21 23:59
                              'weekly_saturday': '3B 17 B9 2C',  # 25.12.21 23:59
                              'daily': '3B 17 BF 2C',  # 31.12.21 23:59,
                              'hourly': '3B 17 BF 2C'}  # 31.12.21 23:59

intervals_dict = {'yearly': ' 01 00',
                  'monthly_middle': ' 02 00',
                  'monthly_end': ' 03 00',
                  'weekly_sunday': ' 04 00',
                  'weekly_monday': ' 05 00',
                  'weekly_tuesday': ' 06 00',
                  'weekly_wednesday': ' 07 00',
                  'weekly_thursday': ' 08 00',
                  'weekly_friday': ' 09 00',
                  'weekly_saturday': ' 0A 00',
                  'daily': ' 0B 00',
                  'hourly': ' 0C 00'}

# ***************************************************************************************
# Global parameters
# ****************************************************************************************
PRIMARY_INSTANCE: str = "00"
SECONDARY_INSTANCE: str = "01"
STATUS_OK: str = '00'
CHECKSUM_SIZE: int = 2
PAGE_SIZE: int = 256
MATCH: int = 1
DATE_AND_TIME_OK: int = 1
DATA_SET_OK: int = 1
MISMATCH: int = 0
NEXT_ENTRY_TIME: str = "3B 37 BC 22"  # 28.02.2021 23:59
INDEX_1022 = 'FE 03'
INDEX_1023 = 'FF 03'
INDEX_30 = '1E 00'
INDEX_31 = '1F 00'
INTERVAL_SELECTOR = "0C 00"


# ***************************************************************************************
# Internal functions
# ****************************************************************************************


def debug_logger(any_str, nr):
    file = open("Debug_log" + str(nr) + ".txt", "a")
    file.write(any_str + "\n")


def convert_lsb_to_msb(data, amount_of_bytes):
    data = data[::-1]
    data = data.split(" ")
    _data = ""
    for x in range(0, amount_of_bytes):
        data[x] = data[x][::-1]
        _data = _data + data[x]
    return _data


def parse_data_set_from_response_read_history_log(response):
    _response = response.split(" 1D 80 00 ")
    data_set = _response[1]
    data_set = data_set[:-9]

    return data_set


def string_to_binary(data, amount_of_bytes):
    data = reversed(data.split())
    return int(''.join(data), 16)


def binary_to_string_2_byte(data):
    data = f'{data:04X}'
    return data[2:] + data[:2]


def get_history_log_data(init, instance_select, data):
    # read from history log: nrOfEntries
    history_data = send_command(init, 'getHistoryLogInfo', instance_select, return_parameters=[data])[data]
    return history_data


def create_history_log(init, instance_select='both'):
    # instance: '00' , '01', 'both'
    if instance_select == 'both':
        entries = [get_history_log_data(init, '00', 'nrOfEntries'), get_history_log_data(init, '01', 'nrOfEntries')]
    else:
        entries = [get_history_log_data(init, instance_select, 'nrOfEntries')]

    if '00 00' in entries:
        if instance_select == 'both':
            # primary:
            send_command(init, 'controlHistoryLog', '01 00')
            send_command(init, 'configureHistoryLogInterval', '00 0C 00')
            # secondary:
            send_command(init, 'controlHistoryLog', '01 01')
            send_command(init, 'configureHistoryLogInterval', '01 0C 00')
        else:
            send_command(init, 'controlHistoryLog', f'01 {instance_select}')
            send_command(init, 'configureHistoryLogInterval', f'{instance_select} 0C 00')

    type_f_time = '3B 37 BC 22'  # 28.02.2021 23:59
    send_command(init, 'Set_rtcDateAndTime', type_f_time)

    loop_count = 0
    while '00 00' in entries:
        sleep(10)
        if instance_select == 'both':
            entries = [get_history_log_data(init, '00', 'nrOfEntries'), get_history_log_data(init, '01', 'nrOfEntries')]
        else:
            entries = [get_history_log_data(init, instance_select, 'nrOfEntries')]
        if loop_count > 18:  # in 3 minutes logs should be created
            break
        loop_count += 1


def analyse_data_set(data_set, selector, volume, timestamp):
    selector = int(selector, 16)
    selector_dict = {}

    chosen_selectors = [element for element in HistoryLogDataSetBitPlaces if selector & element.value]
    for chosen_selector in chosen_selectors:
        sec_elements = [sec_element for sec_element in HistoryLogDataSetSizes if sec_element == chosen_selector.name]
        for sec_element in sec_elements:
            selector_dict[sec_element] = HistoryLogDataSetSizes[sec_element]

    begin_intern = 0
    end_intern = begin_intern
    for element in selector_dict:
        end_intern += selector_dict[element] * 2

        value = data_set[begin_intern:end_intern]

        if element == HistoryLogDataSetBitPlaces.VOLUME_SUM.name or \
                element == HistoryLogDataSetBitPlaces.VOLUME_FORWARD.name or \
                element == HistoryLogDataSetBitPlaces.VOLUME_BACKWARD.name:
            if value != volume:
                return '-01'

        elif element == HistoryLogDataSetBitPlaces.DATETIME_TYPE_F.name:
            if value[2:] != timestamp[2:]:
                return '-01'

        elif element == HistoryLogDataSetBitPlaces.DATETIME_TYPE_G.name:
            if value != timestamp[4:]:
                return '-01'

        begin_intern = end_intern
    return '00'


def configure_data_selector_and_get_data_size(init, instance, data_selector):
    command = 'configureHistoryLogDataset'
    parameter = instance + data_selector
    send_command(init, command, parameters=parameter)
    command = 'getHistoryLogInfo'
    parameter = instance
    response = send_command(init, command, parameters=parameter, return_parameters=['dataSize', 'nrOfPossibleEntries',
                                                                                    'nrOfEntries'])
    data_set_size = response['dataSize']
    nr_of_possible_entries = response['nrOfPossibleEntries']
    nr_of_entries = response['nrOfEntries']

    return data_set_size, nr_of_possible_entries, nr_of_entries


def trigger_history_log_data_set_generation(init):
    command = 'triggerHistoryLogDatasetGeneration'
    parameter = ''
    send_command(init, command, parameters=parameter)


def get_logs_info(init) -> dict:
    primary_info = send_command(init, 'getHistoryLogInfo', PRIMARY_INSTANCE, return_parameters=['dataSelector',
                                                                                                'intervalSelector',
                                                                                                'nrOfEntries',
                                                                                                'nrOfPossibleEntries',
                                                                                                'dataSize',
                                                                                                'instanceStatus'])

    secondary_info = send_command(init, 'getHistoryLogInfo', SECONDARY_INSTANCE,
                                  return_parameters=['dataSelector',
                                                     'intervalSelector',
                                                     'nrOfEntries',
                                                     'nrOfPossibleEntries',
                                                     'dataSize',
                                                     'instanceStatus'])
    return {'primary': primary_info, 'secondary': secondary_info}


def generate_new_log(init, ultrasonic_simulation, iteration, instance):
    number_before = int('0x' + reverse_stream(get_logs_info(init)[instance]['nrOfEntries'], False), 16)
    last_entries_before = get_last_entries(init)

    if iteration < 5:
        # simulate some flow
        ultrasonic_simulation(simulation_mode=UltrasonicSimulationMode.NORMAL, phase_shift_diff=550 * 1024,
                              medium_temperature=270, resonator_calibration=False, time_difference_1us=4000,
                              sonic_speed_correction=19665)
        sleep(5)
        disable_ultrasonic_simulation(init)

    # add new entry
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')

    number_after = int('0x' + reverse_stream(get_logs_info(init)[instance]['nrOfEntries'], False), 16)
    last_entries_after = get_last_entries(init)

    return number_before, last_entries_before, number_after, last_entries_after


def get_last_entries(init):
    # get data sets
    data_set_1022 = send_command(init, "readHistoryLog", SECONDARY_INSTANCE + INDEX_1022 + "01",
                                 return_parameters=['dataSet'])['dataSet']
    data_set_1023 = send_command(init, "readHistoryLog", SECONDARY_INSTANCE + INDEX_1023 + "01",
                                 return_parameters=['dataSet'])['dataSet']
    data_set_30 = send_command(init, "readHistoryLog", PRIMARY_INSTANCE + INDEX_30 + "01",
                               return_parameters=['dataSet'])['dataSet']
    data_set_31 = send_command(init, "readHistoryLog", PRIMARY_INSTANCE + INDEX_31 + "01",
                               return_parameters=['dataSet'])['dataSet']
    return {'1022': data_set_1022, '1023': data_set_1023, '30': data_set_30, '31': data_set_31}


def create_new_log_by_time(init):
    send_command(init, 'Set_rtcDateAndTime', NEXT_ENTRY_TIME)
    sleep(120)


def generate_log_get_statuses(init, file, ultrasonic_simulation, instance):
    # get status before
    status_before = get_logs_info(init)[instance]['instanceStatus']
    file.write(f'{instance} status_before: {status_before}\n')

    # generate the log that will overfill the page
    generate_new_log(init, ultrasonic_simulation, 1, instance)

    # get status after
    status_after = get_logs_info(init)[instance]['instanceStatus']
    file.write(f'{instance} status_after: {status_after}\n')

    return status_before, status_after


def generate_entries_with_different_time_stamp(init, amount_of_entries_to_generate):
    for entry_ctr in range(amount_of_entries_to_generate):
        trigger_history_log_data_set_generation(init)

        # generate next time
        new_time = entry_ctr + 1
        string_time = str(new_time)
        while len(string_time) < 8:
            string_time = "0" + string_time

        send_command(init, 'Set_rtcDateAndTime', string_time)

        # prevent software watchdog
        if (entry_ctr % 90) == 0:
            close_irda_communication_window()

    close_irda_communication_window()
    return 0


def get_time_type_f(data_set):
    return data_set[4:12]


def generate_new_volume(entry_ctr):
    number_as_string = str(entry_ctr)
    last_number = number_as_string[-1]
    new_byte = f'{last_number}{last_number}'
    new_string = ''
    for byte_ctr in range(10):
        new_string = new_string + new_byte + ' '
    return new_string


def get_date_and_volume(response_mbus, index):
    slice_date = ''
    slice_volume = ''
    if index == 0:  # last record
        place_date = response_mbus.find("84 04 6D") + 8
        place_volume = place_date + 20
        slice_date = response_mbus[place_date + 1:  place_date + 12]
        slice_volume = response_mbus[place_volume + 1:  place_volume + 12]
    if index == 1:  # second to the last record
        place_date = response_mbus.find("C4 04 6D") + 8
        place_volume = place_date + 20
        slice_date = response_mbus[place_date + 1:  place_date + 12]
        slice_volume = response_mbus[place_volume + 1:  place_volume + 12]
    if index == 2:  # third to the last record
        place_date = response_mbus.find("84 05 6D") + 8
        place_volume = place_date + 20
        slice_date = response_mbus[place_date + 1:  place_date + 12]
        slice_volume = response_mbus[place_volume + 1:  place_volume + 12]

    return slice_date, slice_volume


def preconditions(init, selector, role, set_operation_mode, activate_sitp, max_entries=1000):
    # Setting Operation mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))
    activate_sitp(role)

    # enable both history instances
    send_command(init, "controlHistoryLog", "01")

    # logging interval
    send_command(init, "configureHistoryLogInterval", INTERVAL_SELECTOR)

    send_command(init, "configureHistoryLogDataset", selector)

    send_command(init, "setMaximalAmountOfHistoryLogEntries", max_entries)
    # send_command(init, "setMaximalAmountOfHistoryLogEntries", SECONDARY_INSTANCE + secondary_limitation)

    # delete all entries in both instances
    send_command(init, 'deleteHistoryLog')
    # send_command(init, 'deleteHistoryLog', SECONDARY_INSTANCE)

    logs_info = get_logs_info(init)

    if logs_info['primary']['dataSelector'] != selector:
        raise Exception('dataSelector has not been set correctly')
    if logs_info['primary']['intervalSelector'] != INTERVAL_SELECTOR:
        raise Exception('intervalSelector has not been set correctly')
    # if logs_info['primary']['nrOfPossibleEntries'] != primary_limitation:
    #     raise Exception('nrOfPossibleEntries has not been set correctly')
    if logs_info['primary']['nrOfEntries'] != '00 00':
        raise Exception('nrOfEntries has not been reset to 0')

    if logs_info['secondary']['dataSelector'] != selector:
        raise Exception('dataSelector has not been set correctly')
    if logs_info['secondary']['intervalSelector'] != INTERVAL_SELECTOR:
        raise Exception('intervalSelector has not been set correctly')
    # if logs_info['secondary']['nrOfPossibleEntries'] != secondary_limitation:
    #     raise Exception('nrOfPossibleEntries has not been set correctly')
    if logs_info['secondary']['nrOfEntries'] != '00 00':
        raise Exception('nrOfEntries has not been reset to 0')

    return logs_info


def int_to_hex_string(integer: int) -> str:
    return str(struct.pack(">i", integer).hex()[4:])


def simulate_flow(init: ItepMock, ultrasonic_simulation, direction: str = "forward"):
    phase_shift_int = 550 if direction == 'forward' else -550
    ultrasonic_simulation(simulation_mode=UltrasonicSimulationMode.NORMAL, phase_shift_diff=phase_shift_int * 1024,
                          medium_temperature=270, resonator_calibration=False, time_difference_1us=4000,
                          sonic_speed_correction=19665)
    sleep(5)
    disable_ultrasonic_simulation(init)
    # add new entry
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')


def get_logs_info(init) -> dict:
    primary_info = send_command(init, 'getHistoryLogInfo', return_parameters=['dataSelector',
                                                                              'intervalSelector',
                                                                              'nrOfEntries',
                                                                              'nrOfPossibleEntries',
                                                                              'dataSize',
                                                                              'instanceStatus'])

    return primary_info

def verify_typef_date(date: str) -> bool:
    date.replace(" ", "")
    data_tobin = bin(int(date, base=16))[2:]
    hour = int(data_tobin[12:15], base=2)
    minute = int(data_tobin[2:7], base=2)
    month = int(str(data_tobin[24:27]) + str(data_tobin[16:18]), base=2)
    day = int(data_tobin[19:23], base=2)
    year = int(data_tobin[28:], base=2)
    if not 0 <= hour <= 23:
        return False
    if not 0 <= minute <= 59:
        return False
    if not 1 <= month <= 12:
        return False
    if not 1 <= day <= 31:
        return False
    if not 0 <= year <= 99:
        return False
    return True

# ***************************************************************************************
# External functions
# ****************************************************************************************

### NIE PATRZ NA TO TO TEN SĄŻNY PIERWSZY TEST JA GO NA KONIEC ROBIE XD
@pytest.mark.history_log
@pytest.mark.test_id('e1fc808c-f723-4116-944c-aaad915150c1')
@pytest.mark.req_ids(['F423', 'F424', 'F425', 'F426', 'F427', 'F428', 'F429'])
@pytest.mark.creator('Artur Kulgawczuk')
@pytest.mark.creation_date('01.04.2021')
@allure.title('Reading data and checking resolution')
@allure.description('''This test checks if all the needed informations can be logged by the history log. This test 
should also check if all the values stored in history log entries (besides error state) have the right resolution (1 
digit after coma).''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP', 'LAB', 'TES', 'UTL'])  # ['REP', 'LAB', 'TES', 'UTL']
@pytest.mark.parametrize('selector', ['06 13'])  # TimeTypeF, SumVol, MedTemp, AmbTemp, ErrState
# @pytest.mark.parametrize('primary_limitation, secondary_limitation', [(32, 1024),  # (32, 1024)
#                                                                       (16, 512),  # (16, 512)
#                                                                       (1, 1)])  # (1, 1)
def test_history_log_reading_data_and_resolution(init, activate_sitp, set_operation_mode, role, mode, selector,
                                                 ultrasonic_simulation):
    # PRECONDITIONS
    # Generate forward volume
    ultrasonic_simulation(simulation_mode=UltrasonicSimulationMode.NORMAL, phase_shift_diff=550 * 1024,
                          medium_temperature=270, resonator_calibration=False, time_difference_1us=4000,
                          sonic_speed_correction=19665)
    sleep(5)
    disable_ultrasonic_simulation(init)
    # Generate backward volume
    # ?????
    # trigger error
    # ?????

    # Apply common preconditions before test running
    logs_info = preconditions(init, mode, selector, role, set_operation_mode, activate_sitp)

    # TEST
    # Step 1 Read forward volume from accu

    # Step 2 Read backward volume from accu

    for iterator in range(secondary_limitation + 1):
        send_command(init, 'triggerHistoryLogDatasetGeneration', '')

    # Step 2 get saved number of entries
    entries_in_primary = int('0x' + reverse_stream(get_logs_info(init)['primary']['nrOfEntries'], False), 16)
    entries_in_secondary = int('0x' + reverse_stream(get_logs_info(init)['secondary']['nrOfEntries'], False), 16)

    # Allure report
    allure.attach(f"""
                                    <h2>Test result</h2>
                                    <table style="width:100%">
                                      <tr>
                                        <th>Mode</th>
                                        <th>Role</th>
                                        <th>Primary limitation</th>
                                        <th>Secondary limitation</th>
                                        <th>Primary limitation set</th>
                                        <th>Secondary limitation set</th>
                                        <th>Generated number of Primary logs</th>
                                        <th>Generated number of secondary log</th>
                                      </tr>
                                      <tr align="center">
                                        <td>{mode}</td>
                                        <td>{role}</td>
                                        <td>{primary_limitation}</td>
                                        <td>{secondary_limitation}</td>
                                        <td>{logs_info['primary']['nrOfPossibleEntries']}</td>
                                        <td>{logs_info['secondary']['nrOfPossibleEntries']}</td>
                                        <td>{entries_in_primary}</td>
                                        <td>{entries_in_secondary}</td>
                                      </tr>
                                    </table>
                                    """,
                  'Test result',
                  allure.attachment_type.HTML)

    # Expected results:
    assert logs_info['primary']['nrOfPossibleEntries'] == primary_limitation_lsb
    assert logs_info['secondary']['nrOfPossibleEntries'] == secondary_limitation_lsb
    assert entries_in_primary == primary_limitation
    assert entries_in_secondary == secondary_limitation


@pytest.mark.test_id('2581b63d-aaac-4e8f-9c06-7adf78e8a649')
@pytest.mark.req_ids(['F437, F743, F438, F744'])
@pytest.mark.creator('Artur Kulgawczuk')
@pytest.mark.creation_date('19.04.2021')
@pytest.mark.history_log
@allure.title('Timestamps')
@allure.description('''This test checks if there is a possibility to log both dateTimeTypeF and operatingHours in 
history log on meters supplied externally or by a battery.''')
# @pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP', 'LAB', 'TES', 'UTL'])
def test_history_log_timestamps(init, role,
                                activate_sitp, set_operation_mode):
    # TODO: switch power supply to battery/external, for now there's no command supplied
    # PRECONDITIONS BLOCK
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))
    # TEST BLOCK
    # configure and enable history log
    preconditions(init, HISTORY_LOG_DATA_SELECTOR['dateTimeTypeF'] + HISTORY_LOG_DATA_SELECTOR['operatingHours'],
                  role, set_operation_mode, activate_sitp)
    # generate log entry
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')
    # read first log entry and check whether correct values are logged
    first_entry = send_command(init, "readHistoryLog", parameters="00 00 01", return_parameters=["dataSet"])['dataSet']
    # first, check if the number of bytes matches the datasets used
    log_info = get_logs_info(init)
    data_size = log_info['dataSize']
    data_size = data_size.replace(" ", "")
    # check if length of dataset correct
    length = int(data_size, base=16)
    # 3 + 4 bytes
    expected_length = 7
    # check if valid date
    date_valid = True if verify_typef_date(first_entry.replace(" ", "")[0, 7]) else False
    allure.attach(f"""
                                    <h2>Test result</h2>
                                    <table style="width:100%">
                                      <tr>
                                        <th>Role:</th>
                                        <th>Expected dataSet size:</th>
                                        <th>Actual dataSet size:</th>
                                        <th>Stored date a valid date:</th>
                                      </tr>
                                      <tr align="center">
                                        <td>{role}</td>
                                        <td>{expected_length}</td>
                                        <td>{length}</td>
                                        <td>{date_valid}</td>
                                      </tr>
                                    </table>
                                    """,
                  'Test result',
                  allure.attachment_type.HTML)

    # reset history log
    send_command(init, 'deleteHistoryLog', '')
    # back to default mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # reset metrological log to be sure is not full after open/close metrological accesses
    activate_sitp('MAN')
    send_command_return_response(init, 'controlMetrologicalLog', '02', '')[-1]
    # assertions
    assert date_valid
    assert expected_length == length


@pytest.mark.test_id('ab8fc71c-a9c2-4f3f-a46b-ac6def670d66')
@pytest.mark.req_ids(['F430, F432, F433'])
@pytest.mark.creator('Artur Kulgawczuk')
@pytest.mark.creation_date('19.04.2021')
@pytest.mark.history_log
@allure.title('Configuration of max number of entries')
@allure.description('''This test checks if it is possible to change the maximum number of entries stored in history 
log. If the log is full new entries should overwrite oldest entries.''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP', 'LAB', 'TES', 'UTL'])
def test_history_log_max_number_of_entries(init, mode, role, ultrasonic_simulation,
                                           activate_sitp, set_operation_mode):
    # PRECONDITION BLOCK
    preconditions(init, HISTORY_LOG_DATA_SELECTOR['ALL'], role, set_operation_mode, activate_sitp)
    # check if history log is empty
    # also save log info for later
    log_info_before = get_logs_info(init)
    num_entries_pre = log_info_before["nrOfEntries"]
    if num_entries_pre != '00 00':
        raise Exception("History log is not empty!")
    # go to prod or ff mode
    set_operation_mode(OperationMode(mode=mode, operation=MeterOperation.NORMAL))
    # activate role
    activate_sitp(role)
    # set history log capacity to 1096 in hex
    send_command(init, "setMaximalAmountOfHistoryLogEntries", int_to_hex_string(1096))
    # check if the change was propagated (only UTL or TES)
    log_info_after_change = get_logs_info(init)
    for i in range(0, 1096):
        nr_of_entries_pre_loop = get_logs_info(init)['nrOfEntries']
        simulate_flow(init, ultrasonic_simulation)
        send_command(init, 'triggerHistoryLogDatasetGeneration', '')
        nr_of_entries_post_loop = get_logs_info(init)['nrOfEntries']
        if nr_of_entries_pre_loop != nr_of_entries_post_loop - 1:
            raise Exception("Entry" + str(i) + "wasn't added!")
    log_info_before_rollout = get_logs_info(init)
    instance_status_before_rollout = log_info_before_rollout['instanceStatus']
    num_log_entries_before_rollout = log_info_before_rollout['nrOfLogEntries']
    # second to last entry
    second_to_last_entry = \
        send_command(init, "readHistoryLog", parameters=int_to_hex_string(1094) + "01", return_parameters=["dataSet"])[
            'dataSet']
    # add one more entry
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')
    #  check number of logs and save the flag
    log_info_after_rollout = get_logs_info(init)
    instance_status_after_rollout = log_info_after_rollout['instanceStatus']
    num_log_entries_after_rollout = log_info_after_rollout['nrOfLogEntries']
    # read last entry in history log
    last_entry = \
        send_command(init, "readHistoryLog", parameters=int_to_hex_string(1095) + "01", return_parameters=["dataSet"])[
            'dataSet']

    allure.attach(f"""
                                    <h2>Test result</h2>
                                    <table style="width:100%">
                                      <tr>
                                        <th>Mode:</th>
                                        <th>Role:</th>
                                        <th>[Before] Number of entries:</th>
                                        <th>[After] Number of entries:</th>
                                        <th>[Before] Instance status:</th>
                                        <th>[After] Instance status:</th>
                                      </tr>
                                      <tr align="center">
                                        <td>{mode}</td>
                                        <td>{role}</td>
                                        <td>{num_log_entries_before_rollout}</td>
                                        <td>{num_log_entries_after_rollout}</td>
                                        <td>{instance_status_before_rollout}</td>
                                        <td>{instance_status_after_rollout}</td>
                                      </tr>
                                    </table>
                                    """,
                  'Test result',
                  allure.attachment_type.HTML)
    # reset history log
    send_command(init, 'deleteHistoryLog', '')
    # back to default mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # reset metrological log to be sure is not full after open/close metrological accesses
    activate_sitp('MAN')
    send_command_return_response(init, 'controlMetrologicalLog', '02', '')[-1]
    # assertions
    assert num_log_entries_before_rollout == num_log_entries_after_rollout
    assert instance_status_after_rollout != instance_status_before_rollout
    assert last_entry == second_to_last_entry


def check_if_element_non_zero(element: str) -> bool:
    non_zero_vals = filter(lambda a: a[1] != "0", enumerate(element[:]))
    if not non_zero_vals:
        return False
    return True


@pytest.mark.test_id('cd96d7b4-fbe4-49f0-b0a2-c14aa26d1211')
@pytest.mark.req_ids(['NoReq'])
@pytest.mark.creator('Artur Kulgawczuk')
@pytest.mark.creation_date('03.11.2020')
@pytest.mark.history_log
@allure.title('Deleting history log by different commands')
@allure.description('''This test checks if history log is deleted after using one of the commands that should cause 
history log deletion. These are: 'Set_ldacm_data_outputVolumeDecimalPlace', 'configureDigitHighlighting'.''')
@pytest.mark.parametrize('command_set, command_get, command_ret', [('Set_ldacm_data_outputVolumeDecimalPlace',
                                                                    'Get_ldacm_data_outputVolumeDecimalPlace',
                                                                    'ldacm_data_outputVolumeDecimalPlace'),
                                                                   ('configureDigitHighlighting,'
                                                                    ' "get_dummy',
                                                                    "return_param_dummy")])
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP', 'LAB', 'TES', 'UTL'])
def test_history_log_deleting_log_by_different_commands(init, activate_sitp, set_operation_mode, role, mode,
                                                        ultrasonic_simulation, command_set, command_get, command_ret):
    # PRECONDITION BLOCK

    # simulate flow
    simulate_flow(init, ultrasonic_simulation)
    # common precondition handling
    preconditions(init, HISTORY_LOG_DATA_SELECTOR['ALL'], role, set_operation_mode, activate_sitp)
    # check if history log is empty
    # also save log info for later
    log_info = get_logs_info(init)
    num_entries_pre = log_info["nrOfEntries"]
    if num_entries_pre != '00 00':
        raise Exception("History log is not empty!")

    # TEST BLOCK
    activate_sitp(role)
    # trigger history log generation
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')

    # read log content
    first_entry = send_command(init, "readHistoryLog", parameters="00 00 01", return_parameters=["dataSet"])['dataSet']
    # check if the first element is non zero
    if not check_if_element_non_zero(first_entry):
        raise Exception("First element is equal to 0!")

    # get initial value of tested command
    command_value = send_command(init, command_get, return_parameters=[command_ret])[command_ret]

    # set the value to sth else
    send_command(init, command_set, parameters="06")

    # change the value back
    send_command(init, command_set, parameters=command_value)

    # check log entries after execution of command
    first_entry_after = send_command(init, "readHistoryLog", parameters="00 00 01", return_parameters=["dataSet"])[
        'dataSet']
    # print('NUMBER OF LOG ENTRIES AFTER DELETION: ' + num_entries_pre + '  ' + number_of_entries_before_2)

    # check success of calling command
    command_succeeded = not check_if_element_non_zero(first_entry_after)
    num_entries_post = get_logs_info(init)["nrOfEntries"]

    allure.attach(f"""
                                    <h2>Test result</h2>
                                    <table style="width:100%">
                                      <tr>
                                        <th>Command:</th>
                                        <th>Mode:</th>
                                        <th>Role:</th>
                                        <th>Tested instance:</th>
                                        <th>[Before] Number of entries:</th>
                                        <th>[After] Number of entries:</th>
                                      </tr>
                                      <tr align="center">
                                        <td>{command_set}</td>
                                        <td>{mode}</td>
                                        <td>{role}</td>
                                        <td>{num_entries_pre}</td>
                                        <td>{num_entries_post}</td>
                                      </tr>
                                    </table>
                                    """,
                  'Test result',
                  allure.attachment_type.HTML)

    # back to default mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # reset metrological log to be sure is not full after open/close metrological accesses
    activate_sitp('MAN')
    send_command_return_response(init, 'controlMetrologicalLog', '02', '')[-1]

    # main assertion
    assert command_succeeded


@pytest.mark.test_id('8cc22a94-311c-45d7-811d-fd4e335d9ff6')
@pytest.mark.req_ids(['F435, F436'])
@pytest.mark.creator('Artur Kulgawczuk')
@pytest.mark.creation_date('03.11.2020')
@pytest.mark.history_log
@allure.title('Logging interval')
@allure.description('''Test checks if the logging interval of the history log can be set to daily or hourly. Log 
should be generated automatically after logging interval time passes.''')
# @pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP', 'LAB', 'TES', 'UTL'])
@pytest.mark.parametrize('interval', ["daily", "hourly"])
def test_history_log_logging_interval(init, activate_sitp, set_operation_mode, role, mode,
                                      interval):
    # PRECONDITION BLOCK
    # common precondition handling
    preconditions(init, HISTORY_LOG_DATA_SELECTOR['ALL'], role, set_operation_mode, activate_sitp)
    # check if history log is empty
    # also save log info for later
    log_info = get_logs_info(init)
    num_entries_pre = log_info["nrOfEntries"]
    if num_entries_pre != '00 00':
        raise Exception("History log is not empty!")
    # enter production mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))
    # TEST BLOCK
    start_time = '00 00 BF 2C'  # 31.12.21 00:00
    send_command(init, 'Set_rtcDateAndTime', start_time)
    send_command(init, "configureHistoryLogInterval", intervals_dict[interval])
    # trigger history log generation, 1 hour interval
    start_time_interval = '00 01 BF 2C' if interval == 'hourly' else '00 00 C1 21'  # 31.12.21 01:00 or 01.01.2022
    send_command(init, 'Set_rtcDateAndTime', start_time_interval)

    # read log content
    first_entry = send_command(init, "readHistoryLog", parameters="0000 01", return_parameters=["dataSet"])['dataSet']
    # check if the first element is non zero

    # check success of calling command
    command_succeeded = check_if_element_non_zero(first_entry)
    num_entries_post = get_logs_info(init)["nrOfEntries"]

    allure.attach(f"""
                                    <h2>Test result</h2>
                                    <table style="width:100%">
                                      <tr>
                                        <th>Mode:</th>
                                        <th>Role:</th>
                                        <th>[Before] Number of entries:</th>
                                        <th>[After] Number of entries:</th>
                                      </tr>
                                      <tr align="center">
                                        <td>{mode}</td>
                                        <td>{role}</td>
                                        <td>{num_entries_pre}</td>
                                        <td>{num_entries_post}</td>
                                        
                                      </tr>
                                    </table>
                                    """,
                  'Test result',
                  allure.attachment_type.HTML)

    # back to default mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # reset metrological log to be sure is not full after open/close metrological accesses
    activate_sitp('MAN')
    send_command_return_response(init, 'controlMetrologicalLog', '02', '')[-1]
    # delete history log
    send_command(init, 'deleteHistoryLog', '')

    # main assertion
    assert command_succeeded
    assert num_entries_post == 1


@pytest.mark.test_id('95148b0f-702e-471b-8653-9ea27c3c7cba')
@pytest.mark.req_ids(['NoReq'])
@pytest.mark.creator('Artur Kulgawczuk')
@pytest.mark.creation_date('03.11.2020')
@pytest.mark.history_log
@allure.title('History log after reset')
@allure.description('''This test checks if history log is kept intact after resetting the meter.''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP', 'LAB', 'TES', 'UTL'])
def test_history_log_after_reset(init, activate_sitp, set_operation_mode, role, mode,
                                 ultrasonic_simulation):
    # PRECONDITION BLOCK
    preconditions(init, mode, HISTORY_LOG_DATA_SELECTOR['ALL'], role, set_operation_mode, activate_sitp)
    # check if history log is empty
    # also save log info for later
    log_info_before = get_logs_info(init)
    num_entries_pre = log_info_before["nrOfEntries"]
    if num_entries_pre != '00 00':
        raise Exception("History log is not empty!")

    # TEST BLOCK
    # generate 100 logs with flow simulation in between
    # store added entries in a list
    entries_before_reset = []
    for i in range(0, 100):
        # simulate flow
        simulate_flow(init, ultrasonic_simulation)
        # trigger history log generation
        send_command(init, 'triggerHistoryLogDatasetGeneration', '')
        # save entries in a list
        entries_before_reset.append(
            send_command(init, "readHistoryLog", parameters="00 00 01", return_parameters=["dataSet"])['dataSet'])
    # save the number of entries in log along with the number of possible entries and other log info
    log_info_before = get_logs_info(init)
    # reset the meter and wait for the meter to go back online
    send_command(init, 'LowLevelPowerAndReset', parameters='06')
    sleep(2)
    # store entries after reset in a list
    entries_after_reset = []
    for i in reversed(range(0, 100)):
        entries_after_reset.append(
            send_command(init, "readHistoryLog", parameters=int_to_hex_string(i) + "01", return_parameters=["dataSet"])[
                'dataSet'])
    # check entry number
    log_info_after = get_logs_info(init)
    num_entries_post = log_info_after['nrOfEntries']
    num_entries_pre = log_info_before["nrOfEntries"]
    # get number of possible entries pre and post
    num_possible_post = log_info_after['nrOfPossibleEntries']
    num_possible_pre = log_info_before['nrOfPossibleEntries']

    allure.attach(f"""
                                    <h2>Test result</h2>
                                    <table style="width:100%">
                                      <tr>
                                        <th>Mode:</th>
                                        <th>Role:</th>
                                        <th>[Before] Number of entries:</th>
                                        <th>[After] Number of entries:</th>
                                        <th>[Before] Number of  possible entries:</th>
                                        <th>[After] Number of possible entries:</th>
                                      </tr>
                                      <tr align="center">
                                        <td>{mode}</td>
                                        <td>{role}</td>
                                        <td>{num_entries_pre}</td>
                                        <td>{num_entries_post}</td>
                                        <td>{num_possible_pre}</td>
                                        <td>{num_possible_post}</td>
                                      </tr>
                                    </table>
                                    """,
                  'Test result',
                  allure.attachment_type.HTML)

    # delete log and back to default mode
    send_command(init, 'deleteHistoryLog', '')
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # reset metrological log to be sure is not full after open/close metrological accesses
    activate_sitp('MAN')
    send_command_return_response(init, 'controlMetrologicalLog', '02', '')[-1]

    # main assertion
    assert num_entries_post == num_entries_pre
    assert num_possible_post == num_possible_pre
    assert entries_before_reset == entries_after_reset


@pytest.mark.test_id('4db4a0d7-a727-4fd3-9b23-391514253e34')
@pytest.mark.req_ids(['F431, F153'])
@pytest.mark.creator('Artur Kulgawczuk')
@pytest.mark.creation_date('03.11.2020')
@pytest.mark.history_log
@allure.title('Generating and deleting entries')
@allure.description(
    '''Test checks if it is possible to generate and delete logs from history log in correct modes and roles.''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP', 'LAB', 'TES', 'UTL'])
def test_history_log_generating_and_deleting_entries(init, activate_sitp, set_operation_mode, role, mode,
                                                     ultrasonic_simulation):
    # PRECONDITION BLOCK
    preconditions(init, HISTORY_LOG_DATA_SELECTOR['ALL'], role, set_operation_mode, activate_sitp)
    # check if history log is empty
    log_info_before = get_logs_info(init)
    num_entries_pre = log_info_before["nrOfEntries"]
    if num_entries_pre != '00 00':
        raise Exception("History log is not empty!")
    set_operation_mode(OperationMode(mode=mode, operation=MeterOperation.NORMAL))
    # TEST BLOCK
    # switch to certain roles
    activate_sitp(role)
    # simulate flow and trigger dataset generation
    simulate_flow(init, ultrasonic_simulation)
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')
    # read the first entry
    first_entry = send_command(init, "readHistoryLog", parameters="00 00 01", return_parameters=["dataSet"])['dataSet']
    # check if the entry is not null
    if not check_if_element_non_zero(first_entry):
        raise Exception("The first entry is null!")
    # clear history log
    send_command(init, 'deleteHistoryLog', '')
    # read the first entry
    first_entry_after = send_command(init, "readHistoryLog", parameters="00 00 01", return_parameters=["dataSet"])[
        'dataSet']

    # check entry number
    log_info_after = get_logs_info(init)
    num_entries_post = log_info_after['nrOfEntries']
    num_entries_pre = log_info_before["nrOfEntries"]

    allure.attach(f"""
                                    <h2>Test result</h2>
                                    <table style="width:100%">
                                      <tr>
                                        <th>Mode:</th>
                                        <th>Role:</th>
                                        <th>[Before] Number of entries:</th>
                                        <th>[After] Number of entries:</th>
                                      </tr>
                                      <tr align="center">
                                        <td>{mode}</td>
                                        <td>{role}</td>
                                        <td>{num_entries_pre}</td>
                                        <td>{num_entries_post}</td>
                                      </tr>
                                    </table>
                                    """,
                  'Test result',
                  allure.attachment_type.HTML)

    # back to default mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # reset metrological log to be sure is not full after open/close metrological accesses
    activate_sitp('MAN')
    send_command_return_response(init, 'controlMetrologicalLog', '02', '')[-1]

    # main assertion
    if mode == "UTL" or mode == 'TES':
        assert num_entries_post == 0 and not check_if_element_non_zero(first_entry_after)
    else:
        assert num_entries_post == num_entries_pre
