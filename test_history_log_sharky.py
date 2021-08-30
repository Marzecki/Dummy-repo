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


def preconditions(init, selector, role, set_operation_mode, activate_sitp, max_entries='E8 03'):
    # Setting Operation mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))
    activate_sitp(role)

    # enable history log
    send_command(init, "controlHistoryLog", "01")

    # logging interval
    send_command(init, "configureHistoryLogInterval", INTERVAL_SELECTOR)

    send_command(init, "configureHistoryLogDataset", selector)

    send_command(init, "setMaximalAmountOfHistoryLogEntries", max_entries)

    # delete all entries
    send_command(init, 'deleteHistoryLog')

    logs_info = get_logs_info(init)

    if logs_info['dataSelector'] != selector:
        raise Exception('dataSelector has not been set correctly')
    if logs_info['intervalSelector'] != INTERVAL_SELECTOR:
        raise Exception('intervalSelector has not been set correctly')
    if logs_info['nrOfEntries'] != '00 00':
        raise Exception('nrOfEntries has not been reset to 0')

    return logs_info


def int_to_hex_string(integer: int, num_bytes: int) -> str:
    return integer.to_bytes(num_bytes, 'little').hex().upper()


def simulate_flow(init: ItepMock, ultrasonic_simulation, direction: str = "forward"):
    phase_shift_int = 550 if direction == 'forward' else -550
    ultrasonic_simulation(simulation_mode=UltrasonicSimulationMode.NORMAL, phase_shift_diff=phase_shift_int * 1024,
                          medium_temperature=270, resonator_calibration=False, time_difference_1us=4000,
                          sonic_speed_correction=19665)
    sleep(5)
    disable_ultrasonic_simulation(init)


def get_logs_info(init) -> dict:
    primary_info = send_command(init, 'getHistoryLogInfo', return_parameters=['dataSelector',
                                                                              'intervalSelector',
                                                                              'nrOfEntries',
                                                                              'nrOfPossibleEntries',
                                                                              'dataSize',
                                                                              'instanceStatus'])

    return primary_info


def verify_typef_date(date: str) -> bool:
    date = date.replace(" ", "")
    data_tobin = format((int(date, base=16)), '#034b')[2:]
    hour = int(data_tobin[11:16], base=2)
    minute = int(data_tobin[2:8], base=2)
    day = int(data_tobin[19:24], base=2)
    month = int(data_tobin[27:], base=2)
    year = int(data_tobin[24:27] + data_tobin[15:19], base=2)
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


def check_if_element_non_zero(element: str) -> bool:
    element = element.replace(" ", "")
    non_zero_vals = list(filter(lambda a: a[1] != "0", enumerate(element[:])))
    print(non_zero_vals)
    if not non_zero_vals:
        return False
    return True


# ***************************************************************************************
# External functions
# ****************************************************************************************

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
def test_history_log_reading_data_and_resolution(init, activate_sitp, set_operation_mode, role, mode, selector,
                                                 ultrasonic_simulation):
    # PRECONDITION BLOCK
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')
    send_command(init, 'Set_ldacm_data_volumeDefinitionsAccu1', int_to_hex_string(21152115, 10))
    send_command(init, 'Set_ldacm_data_volumeDefinitionsAccu2', int_to_hex_string(2115, 10))
    # TODO: generate error, not sure if command final
    send_command(init, 'ReportErrorState', "00 00 00 04")
    preconditions(init, int_to_hex_string(HISTORY_LOG_DATA_SELECTOR['forwardVolume']
                                          + HISTORY_LOG_DATA_SELECTOR['backwardVolume']
                                          + HISTORY_LOG_DATA_SELECTOR['mediumTemperature']
                                          + HISTORY_LOG_DATA_SELECTOR['errorState']
                                          + HISTORY_LOG_DATA_SELECTOR['maxForwardFlow']
                                          + HISTORY_LOG_DATA_SELECTOR['currentFlow'], 2),
                  role, set_operation_mode, activate_sitp)
    # set op mode to parametrised
    set_operation_mode(OperationMode(mode=mode, operation=MeterOperation.NORMAL))
    # TEST BLOCK
    # read forward volume from accu
    forward_volume = send_command(init, 'Get_ldacm_data_volumeDefinitionsAccu1',
                                  return_parameters=["ldacm_data_volumeDefinitionsAccu1"])[
        "ldacm_data_volumeDefinitionsAccu1"]
    # read backward volume from accu
    back_volume = send_command(init, 'Get_ldacm_data_volumeDefinitionsAccu2',
                               return_parameters=["ldacm_data_volumeDefinitionsAccu2"])[
        "ldacm_data_volumeDefinitionsAccu2"]
    # read current medium temperature
    medium_temp = send_command(init, 'TestTemperatureMeasurement',
                               return_parameters=["ntc temperature"])["ntc temperature"]
    # read error state
    error_state = send_command(init, 'getErrorState',
                               return_parameters=["pendingErrors"])["pendingErrors"]

    # read maximum forward flowrate
    # TODO: no command supplied yet
    # read current flowrate
    current_flowrate = send_command(init, 'Get_ldacm_data_selfDisclosure_flowRateQ3',
                                    return_parameters=["ldacm_data_selfDisclosure_flowRateQ3"])[
        "ldacm_data_selfDisclosure_flowRateQ3"]
    for i in range(0, 30):
        send_command(init, 'triggerHistoryLogDatasetGeneration', '')

    first_entry = send_command(init, "readHistoryLog", parameters="00 00 01", return_parameters=["dataSet"])[
        'dataSet'].replace(" ", "")

    # extract values from first entry
    hl_forward_volume = first_entry[:8]
    hl_back_volume = first_entry[8:16]
    hl_medium_temp = first_entry[16:20]
    hl_error_state = first_entry[20:28]
    # TODO: compare max flow, no command yet

    allure.attach(f"""
                                        <h2>Test result</h2>
                                        <table style="width:100%">
                                          <tr>
                                            <th>Mode:</th>
                                            <th>[Accu]: Forward volume</th>
                                            <th>[HistoryLog]: Forward volume</th>
                                            <th>[Accu]: Backward volume</th>
                                            <th>[HistoryLog]: Backward volume</th>
                                            <th>[Accu]: Medium temp </th>
                                            <th>[HistoryLog]: Medium temp</th>
                                            <th>[Accu]: Error state</th>
                                            <th>[HistoryLog]: Error state</th>
                                          </tr>
                                          <tr align="center">
                                            <td>{mode}</td>
                                            <td>{role}</td>
                                            <td>{forward_volume}</td>
                                            <td>{hl_forward_volume}</td>
                                            <td>{back_volume}</td>
                                            <td>{hl_back_volume}</td>
                                            <td>{medium_temp}</td>
                                            <td>{hl_medium_temp}</td>
                                            <td>{error_state}</td>
                                            <td>{hl_error_state}</td>
                                          </tr>
                                        </table>
                                        """,
                  'Test result',
                  allure.attachment_type.HTML)

    # back to default mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # reset metrological log to be sure is not full after open/close metrological accesses
    send_command(init, 'controlMetrologicalLog', parameters='02')

    # main assertion
    assert forward_volume == hl_forward_volume
    assert back_volume == hl_back_volume
    assert medium_temp == hl_medium_temp
    assert error_state == hl_error_state
    # TODO: compare max flow, no command yet



@pytest.mark.test_id('2581b63d-aaac-4e8f-9c06-7adf78e8a649')
@pytest.mark.req_ids(['F437, F743, F438, F744'])
@pytest.mark.creator('Artur Kulgawczuk')
@pytest.mark.creation_date('19.04.2021')
@pytest.mark.history_log
@allure.title('Timestamps')
@allure.description('''This test checks if there is a possibility to log both dateTimeTypeF and operatingHours in 
history log on meters supplied externally or by a battery.''')
def test_history_log_timestamps(init, activate_sitp, set_operation_mode):
    # TODO: switch power supply to battery/external, for now there's no command supplied
    # PRECONDITIONS BLOCK
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))
    # TEST BLOCK
    # configure and enable history log
    preconditions(init, int_to_hex_string(HISTORY_LOG_DATA_SELECTOR['dateTimeTypeF'] +
                                          HISTORY_LOG_DATA_SELECTOR['operatingHours'], 2),
                  'MAN', set_operation_mode, activate_sitp)
    # generate log entry
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')
    # read first log entry and check whether correct values are logged
    first_entry = send_command(init, "readHistoryLog", parameters="00 00 01", return_parameters=["dataSet"])['dataSet']
    # first, check if the number of bytes matches the datasets used
    data_size = first_entry.replace(" ", "")
    # get expected length in lsb to compare with data_size
    expected_length = int_to_hex_string(HistoryLogDataSetSizes['dateTimeTypeF'] + HistoryLogDataSetSizes['operatingHours'], 1)
    # check if valid date
    date_valid = True if verify_typef_date(first_entry.replace(" ", "")[0, 7]) else False
    allure.attach(f"""
                                    <h2>Test result</h2>
                                    <table style="width:100%">
                                      <tr>
                                        <th>Expected dataSet size:</th>
                                        <th>Actual dataSet size:</th>
                                        <th>Stored date a valid date:</th>
                                      </tr>
                                      <tr align="center">
                                        <td>{expected_length}</td>
                                        <td>{data_size}</td>
                                        <td>{date_valid}</td>
                                      </tr>
                                    </table>
                                    """,
                  'Test result',
                  allure.attachment_type.HTML)

    # reset history log
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))
    send_command(init, 'deleteHistoryLog', '')
    # back to default mode

    # reset metrological log to be sure is not full after open/close metrological accesses
    send_command(init, 'controlMetrologicalLog', parameters='02')
    # assertions
    assert date_valid
    assert expected_length == data_size


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
    # handle preconditions
    # check if history log is empty
    # also save log info for later
    preconditions(init, int_to_hex_string(HISTORY_LOG_DATA_SELECTOR['ALL'], 2), role,
                  set_operation_mode, activate_sitp)
    # go to prod or ff mode
    set_operation_mode(OperationMode(mode=mode, operation=MeterOperation.NORMAL))
    # activate role
    activate_sitp(role)
    # set history log capacity to 1096 in hex
    send_command(init, "setMaximalAmountOfHistoryLogEntries", int_to_hex_string(1096, 2))
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
        send_command(init, "readHistoryLog", parameters=int_to_hex_string(1094, 2) + "01",
                     return_parameters=["dataSet"])[
            'dataSet']
    # add one more entry
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')
    #  check number of logs and save the flag
    log_info_after_rollout = get_logs_info(init)
    instance_status_after_rollout = log_info_after_rollout['instanceStatus']
    num_log_entries_after_rollout = log_info_after_rollout['nrOfLogEntries']
    # read last entry in history log
    last_entry = \
        send_command(init, "readHistoryLog", parameters=int_to_hex_string(1095, 2) + "01",
                     return_parameters=["dataSet"])[
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
    send_command(init, 'controlMetrologicalLog', parameters='02')
    # assertions
    if role == 'UTL' or 'TES':
        assert log_info_after_change['nrOfPossibleEntries'] == int_to_hex_string(1096, 2)
    assert num_log_entries_before_rollout == num_log_entries_after_rollout
    assert instance_status_after_rollout != instance_status_before_rollout
    assert last_entry == second_to_last_entry


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
    log_info = preconditions(init, int_to_hex_string(HISTORY_LOG_DATA_SELECTOR['ALL'], 2), role, set_operation_mode,
                             activate_sitp)
    # check if history log is empty
    # also save log info for later
    num_entries_pre = log_info["nrOfEntries"]

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

    send_command(init, 'controlMetrologicalLog', parameters='02')

    # main assertion
    assert num_entries_post == '00 00'
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
    # check if history log is empty
    # also save log info for later
    num_entries_pre = preconditions(init, int_to_hex_string(HISTORY_LOG_DATA_SELECTOR['ALL'], 2), role,
                                    set_operation_mode, activate_sitp)['nrOfEntries']

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
    send_command(init, 'controlMetrologicalLog', parameters='02')
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
    # check if history log is empty
    # also save log info for later
    preconditions(init, mode, int_to_hex_string(HISTORY_LOG_DATA_SELECTOR['ALL'], 2), role, set_operation_mode, activate_sitp)

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
            send_command(init, "readHistoryLog", parameters=int_to_hex_string(i, 2) + "01", return_parameters=["dataSet"])[
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
    send_command(init, 'controlMetrologicalLog', parameters='02')

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
    # check if history log is empty
    log_info_before = preconditions(init, int_to_hex_string(HISTORY_LOG_DATA_SELECTOR['ALL'], 2), role, set_operation_mode, activate_sitp)

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
    send_command(init, 'controlMetrologicalLog', parameters='02')

    # main assertion
    if mode == "UTL" or mode == 'TES':
        assert num_entries_post == 0 and not check_if_element_non_zero(first_entry_after)
    else:
        assert num_entries_post == num_entries_pre


@pytest.mark.test_id('b2c38a0b-7ae3-4e3e-808a-4eb8b1615794')
@pytest.mark.req_ids(['NoReq'])
@pytest.mark.creator('Artur Kulgawczuk')
@pytest.mark.creation_date('03.11.2020')
@pytest.mark.history_log
@allure.title('Reading log with different datasets')
@allure.description(
    '''This test checks if all selected types of information can be logged by the history log in different sets.''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP', 'LAB', 'TES', 'UTL'])
@pytest.mark.parametrize('selectors', [("forwardVolume",), ("backwardVolume",), ("currentFlow",),
                                       ("forwardVolume", "errorState"), ("currentFlow", "mediumTemp"),
                                       ("backwardVolume", "maxBackward"),
                                       ("backwardVolume", "maxBackward", "forwardVolume"),
                                       ("mediumTemp", "maxForward", "errorState"),
                                       ("sumVolume", "currentFlow", "maxForward"), ("ALL",)])
def test_history_log_reading_selected_data(init, activate_sitp, set_operation_mode, role, mode,
                                           selectors):
    # PRECONDITION BLOCK
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')
    send_command(init, 'Set_ldacm_data_volumeDefinitionsAccu1', int_to_hex_string(21152115, 10))
    send_command(init, 'Set_ldacm_data_volumeDefinitionsAccu2', int_to_hex_string(2115, 10))
    # TODO: generate error, not sure if command final
    send_command(init, 'ReportErrorState', "00 00 00 04")
    preconditions(init, int_to_hex_string(HISTORY_LOG_DATA_SELECTOR['ALL'], 2), role, set_operation_mode, activate_sitp)
    # set op mode to parametrised
    set_operation_mode(OperationMode(mode=mode, operation=MeterOperation.NORMAL))

    # TEST BLOCK
    # configure datasets
    selector = 0
    for sel in selectors:
        selector += HISTORY_LOG_DATA_SELECTOR[sel]
    send_command(init, "configureHistoryLogDataset", int_to_hex_string(selector, 2))
    send_command(init, 'triggerHistoryLogDatasetGeneration', '')
    # switch to certain roles
    activate_sitp(role)
    # read the first entry
    first_entry = send_command(init, "readHistoryLog", parameters="00 00 01", return_parameters=["dataSet"])['dataSet']. \
        replace(" ", "")
    sel_data_size = 0
    for sel in selectors:
        sel_data_size += HistoryLogDataSetSizes[sel]

    actual_entry_length = len(first_entry)

    allure.attach(f"""
                                    <h2>Test result</h2>
                                    <table style="width:100%">
                                      <tr>
                                        <th>Mode:</th>
                                        <th>Role:</th>
                                        <th>Selectors:</th>
                                        <th>Expected data size:</th>
                                        <th>Actual data size:</th>
                                      </tr>
                                      <tr align="center">
                                        <td>{mode}</td>
                                        <td>{role}</td>
                                        <td>{selectors}</td>
                                        <td>{sel_data_size}</td>
                                        <td>{actual_entry_length}</td>
                                      </tr>
                                    </table>
                                    """,
                  'Test result',
                  allure.attachment_type.HTML)

    # back to default mode
    set_operation_mode(OperationMode(mode=MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # reset metrological log to be sure is not full after open/close metrological accesses
    send_command(init, 'controlMetrologicalLog', parameters='02')

    # main assertion
    assert actual_entry_length == sel_data_size
