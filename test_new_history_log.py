import struct

import allure
import pytest
from time import sleep, time
from enum import Enum
from random import randint

from meter_interaction.com_interactions import send_command_return_response
from support.commands_usage import call_command_to_delete_log, is_locked_storage_operation, lock_storage_mode
from meter_interaction import com_interactions
from support.hydrus2.commands import send_command, set_volume_accus, trigger_function, disable_ultrasonic_simulation
from support.hydrus2.communication import close_irda_communication_window, CommunicationMode
from support.hydrus2.errors import CiFieldError
from support.meter_types import OperationMode, MeterOperation, MeterMode, TriggerFunction, UltrasonicSimulationMode
from support.data_parser import reverse_stream, int_to_lsb

from itertools import chain

AMOUNT_OF_HISTORY_LOG_ENTRIES = 30
SUM_VOLUME = "45239178563412000000"
ENABLE_LOG = '01 00'
ERROR_CLASSES = ['00', '01', '02']
DAILY_INTERVAL = '0x000B'
HOURLY_INTERVAL = '0x000C'
REMOVE_COMMANDS = ['deleteHistoryLog']
ERROR_LIST = []
LIST_OF_ENTRIES = []
OUT_OF_HISTORY_LOG_DATA = []
HISTORY_LOG_DATA = []
LIST_OF_ALL_DATA_TYPES = []


def preconditions(init, set_operation_mode, mode, selector):
    # Go to production/field fallback mode
    set_operation_mode(OperationMode(mode=mode, operation=MeterOperation.NORMAL))

    # Enable history log
    send_command(init, 'controlHistoryLog', ENABLE_LOG)

    # Make sure that history log is empty, if not clear it
    response = send_command(init, 'readHistoryLog', parameters='00', return_parameters=['dataSet'])
    check_if_empty = response['dataset']
    if check_if_empty == '0x0':
        pass
    else:
        send_command(init, 'deleteHistoryLog')

    # Configure history log dataset
    send_command(init, 'configureHistoryLogDataset', selector, return_parameters=['returnedCommandBytes'])


def postconditions(init, set_operation_mode):
    # Clear history log
    send_command(init, 'deleteHistoryLog')

    # Go to production mode
    set_operation_mode(OperationMode(MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))


def check_roles(init, mode, activate_sitp, role):
    # Check if meter is in field fallback mode for every possible role
    if mode == MeterMode.FIELD_FALLBACK:
        activate_sitp(role)


@pytest.mark.test_id('e1fc808c-f723-4116-944c-aaad915150c1')
@pytest.mark.req_ids(['F423', 'F424', 'F425', 'F426', 'F427', 'F428', 'F429'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('26.08.2021')
@allure.title('Reading data and checking resolution')
@allure.description('''This test checks if all the needed informations can be logged 
                        by the history log. This test should also check if all
                        the values stored in history log entries (besides error state) 
                        have the right resolution (1 digit after coma).''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP, LAB, TES, UTL'])
def test_history_log_reading_data_and_resolution(init, set_operation_mode, mode, selector, activate_sitp, role):
    # PRECONDITIONS

    preconditions(init, set_operation_mode, mode, selector)

    # Generate some forward/backward volume
    send_command(init, 'Set_ldacm_data_volumeDefinitionsAccu0', SUM_VOLUME)

    # Generate some error
    # TODO: Generate error here

    # TEST STEPS

    check_roles(init, mode, activate_sitp, role)

    # Enable simulation
    send_command(init, 'EnableUltrasonicSimulation', '00')  # Uncompleted command.

    # Clear list to store data here
    OUT_OF_HISTORY_LOG_DATA.clear()

    # Read forward volume from accu
    forward_volume_data = send_command(init, 'Get_ldacm_data_volumeDefinitionsAccu1',
                                       return_parameters=['ldacm_data_volumeDefinitionsAccu1'])
    forward_value = forward_volume_data['ldacm_data_volumeDefinitionsAccu1']
    OUT_OF_HISTORY_LOG_DATA.append(forward_value)

    # Read backward volume from accu
    backward_volume_data = send_command(init, 'Get_ldacm_data_volumeDefinitionsAccu2',
                                        return_parameters=['ldacm_data_volumeDefinitionsAccu2'])
    backward_value = backward_volume_data['ldacm_data_volumeDefinitionsAccu2']
    OUT_OF_HISTORY_LOG_DATA.append(backward_value)

    # Read current medium temperature
    # TODO: Read current medium temperature

    # Make sure that error list is empty
    ERROR_LIST.clear()

    # Read current error state
    for error in ERROR_CLASSES:
        response = send_command(init, 'getErrorState', error, return_parameters=['pendingErrors'])
        value = response['pendingErrors']
        ERROR_LIST.append(value)

    # Add errors to list with data
    OUT_OF_HISTORY_LOG_DATA.append(ERROR_LIST)

    # Read maximum forward flow rate
    # TODO: Read maximum forward flow rate

    # Read current flow rate
    # TODO: Read current flow rate

    # Generate 30 history logs
    for entry in range(AMOUNT_OF_HISTORY_LOG_ENTRIES):
        send_command(init, 'triggerHistoryLogDatasetGeneration', parameters='')

    # Make sure that list of entries is empty
    LIST_OF_ENTRIES.clear()

    # Get 30 logs from "readHistoryLog" command
    for entry in range(AMOUNT_OF_HISTORY_LOG_ENTRIES):
        hex_entry = hex(entry)
        history_log_data = send_command(init, 'readHistoryLog', '00 00 {}'.format(hex_entry),
                                        return_parameters=['dataSet'])

        data_set = history_log_data['dataSet']
        LIST_OF_ENTRIES.append(data_set)

    # POSTCONDITIONS

    postconditions(init, set_operation_mode)
    assert OUT_OF_HISTORY_LOG_DATA == LIST_OF_ENTRIES, "Data from history log and out of it are not equal."
    assert ERROR_LIST != '', "Current error state is empty."


@pytest.mark.test_id('ab8fc71c-a9c2-4f3f-a46b-ac6def670d66')
@pytest.mark.req_ids(['F430', 'F432', 'F433'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('26.08.2021')
@allure.title('Configuration of max number of entries')
@allure.description('''This test checks if it is possible to change the maximum number of entries 
                        stored in history log. If the log is full
                        new entries should overwrite oldest entries.''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP, LAB, TES, UTL'])
def test_history_log_max_number_of_entries(init, activate_sitp, role, mode, set_operation_mode, selector):
    # PRECONDITIONS

    preconditions(init, set_operation_mode, mode, selector)

    # TEST STEPS

    check_roles(init, mode, activate_sitp, role)

    # Set history log capacity to 1096 entries
    if role == 'UTL' or role == 'TES':
        send_command(init, 'setMaximalAmountOfHistoryLogEntries', parameters='00 00 04')

    # Check if history log capacity was saved correctly
        response = send_command(init, 'getHistoryLogInfo', return_parameters=['nrOfPossibleEntries'])
        amount_of_entries = response['nrOfPossibleEntries']
        assert amount_of_entries == '1096', "Incorrect amount of entries."
    else:
        pass

    # Generate logs and fill entire history log with flow simulation between logs
    for entry in range(1096):
        loop_number = 1
        send_command(init, 'triggerHistoryLogDatasetGeneration')
        send_command(init, 'EnableUltrasonicSimulation', '00')  # Uncompleted command.
        log_number = send_command(init, 'getHistoryLohInfo', return_parameters=['nrOfEntries'])
        response = log_number['nrOfEntries']
        response_int = int(response)

        # Check if history log has been incremented by 1
        assert loop_number == response_int, "History log isn't incremented by 1."
        loop_number += 1

    # Read the flag "instanceStatus" - first instance status
    instance_status = send_command(init, 'getHistoryLogInfo', return_parameters=['instanceStatus'])
    first_check_instance_status = instance_status['instanceStatus']

    # Make sure that list of entries is empty
    LIST_OF_ENTRIES.clear()

    # Read second to last entry
    available_entries = send_command(init, 'readHistoryLog', return_parameters=['dataSet'])
    response = available_entries['dataSet']
    LIST_OF_ENTRIES.append(response)
    second_to_last_entry = LIST_OF_ENTRIES[-2]

    # Add one additional entry to history log
    send_command(init, 'triggerHistoryLogDatasetGeneration')

    # Check number of logs in history log
    assert len(LIST_OF_ENTRIES) == 1096, "Number of entries is not equal 1096"

    # Read the flag "instanceStatus" - second instance status
    instance_status = send_command(init, 'getHistoryLogInfo', return_parameters=['instanceStatus'])
    second_check_instance_status = instance_status['instanceStatus']

    last_entry = LIST_OF_ENTRIES[-1]

    # POSTCONDITIONS

    postconditions(init, set_operation_mode)
    assert first_check_instance_status != second_check_instance_status, "Instances should be different."
    assert second_to_last_entry == last_entry, "This entries should be equal."


@pytest.mark.test_id('4db4a0d7-a727-4fd3-9b23-391514253e34')
@pytest.mark.req_ids(['F431', 'F153'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('26.08.2021')
@allure.title('Generating and deleting entries')
@allure.description('''Test checks if it is possible to generate and delete logs 
                        from history log in correct modes and roles.''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP, LAB, TES, UTL'])
def test_history_log_generating_and_deleting_entries(init, mode, role, set_operation_mode, activate_sitp, selector):
    # PRECONDITIONS

    preconditions(init, set_operation_mode, mode, selector)

    # TEST STEPS

    check_roles(init, mode, activate_sitp, role)

    # Generate log
    send_command(init, 'triggerHistoryLogDatasetGeneration')

    # Make sure that list of entries is empty
    LIST_OF_ENTRIES.clear()

    # Read history log content and clear history log if not empty
    response = send_command(init, 'readHistoryLog', parameters='00', return_parameters=['dataSet'])
    check_if_empty = response['dataset']
    LIST_OF_ENTRIES.append(check_if_empty)
    if check_if_empty == '0x0':
        assert "History log should not be empty"
    else:
        send_command(init, 'deleteHistoryLog')
    LIST_OF_ENTRIES.clear()

    # Read history log content
    response = send_command(init, 'readHistoryLog', parameters='00', return_parameters=['dataSet'])
    check_if_empty = response['dataset']
    LIST_OF_ENTRIES.append(check_if_empty)
    if LIST_OF_ENTRIES[0] == '0x0':
        pass
    else:
        assert "History log should be empty"

    # POSTCONDITIONS

    send_command(init, 'deleteHistoryLog')
    set_operation_mode(OperationMode(MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))


@pytest.mark.test_id('8cc22a94-311c-45d7-811d-fd4e335d9ff6')
@pytest.mark.req_ids(['F435', 'F436'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('26.08.2021')
@allure.title('Logging interval')
@allure.description('''Test checks if the logging interval of the history log can be 
                        set to daily or hourly. Log should be generated automatically 
                        after logging interval time passes.''')
@pytest.mark.parametrize('mode', [MeterMode.PRODUCTION])
def test_history_log_logging_interval(init, mode, set_operation_mode, selector):
    # PRECONDITIONS

    preconditions(init, set_operation_mode, mode, selector)

    # TEST STEPS

    # For daily or hourly interval
    # Check method of interval notation
    intervals = [DAILY_INTERVAL, HOURLY_INTERVAL]
    for interval in intervals:
        send_command(init, 'configureHistoryLogInterval', parameters=f'{interval}')

        # Fill an empty history log by simulating time interval
        # Is parameter correct?
        send_command(init, 'Set_rtcDateAndTime', parameters='0x0002')

        # Read history log content
        LIST_OF_ENTRIES.clear()
        response = send_command(init, 'readHistoryLog', parameters='00', return_parameters=['dataSet'])
        check_if_empty = response['dataset']
        LIST_OF_ENTRIES.append(check_if_empty)
        if LIST_OF_ENTRIES[0] == '0x0':
            assert "History log should not be empty"
        else:
            pass

    # POSTCONDITIONS

    postconditions(init, set_operation_mode)


@pytest.mark.test_id('2581b63d-aaac-4e8f-9c06-7adf78e8a649')
@pytest.mark.req_ids(['F437', 'F743', 'F438', 'F744'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('26.08.2021')
@allure.title('Timestamps')
@allure.description('''This test checks if there is a possibility to log both dateTimeTypeF 
                        and operatingHours in history log on meters supplied
                        externally or by a battery.''')
@pytest.mark.parametrize('mode', [MeterMode.PRODUCTION])
def test_history_log_timestamps(init, set_operation_mode, mode, selector):
    # PRECONDITIONS

    preconditions(init, set_operation_mode, mode, selector)

    # TEST STEPS

    # Change the supply method to external/battery
    # TODO: Wait for command to change supply method

    # Enable history log
    send_command(init, 'controlHistoryLog', ENABLE_LOG)

    # Configure log entry
    # Input parameter required to select dataset
    send_command(init, 'configureHistoryLogDataset', selector)

    # Generate log entry
    send_command(init, 'triggerHistoryLogDatasetGeneration')

    # Read first entry to check if dateTimeTypeF and operatingHOURS are there
    LIST_OF_ENTRIES.clear()
    response = send_command(init, 'readHistoryLog', parameters='00', return_parameters=['dataSet'])
    check_if_empty = response['dataset']
    LIST_OF_ENTRIES.append(check_if_empty)
    if '0x0002' and '0x0400' in LIST_OF_ENTRIES:
        pass
    else:
        assert '"dateTimeTypeF and operatingHours are required"'

    # POSTCONDITIONS

    postconditions(init, set_operation_mode)


@pytest.mark.test_id('b2c38a0b-7ae3-4e3e-808a-4eb8b1615794')
@pytest.mark.req_ids(['NoReq'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('26.08.2021')
@allure.title('Reading log with different datasets')
@allure.description('''This test checks if all selected types of information can be 
                        logged by the history log in different sets.''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP, LAB, TES, UTL'])
@pytest.mark.parametrize('selector', '[[fw], [bw], [er], [fw, bw], [bw, er], [bw, er], [all]]')     # Algorithm example
def test_history_log_reading_selected_data(init, mode, role, set_operation_mode, activate_sitp, selector):
    # PRECONDITIONS

    preconditions(init, set_operation_mode, mode, selector)

    # Set forward volume accu
    send_command(init, 'Set_ldacm_data_volumeDefinitionsAccu1', SUM_VOLUME)

    # Generate some error
    # TODO: Generate error here

    # TEST STEPS

    # Get values of volume accus and error state
    ERROR_LIST.clear()
    send_command(init, 'Get_ldacm_data_volumeDefinitionsAccu1', return_parameters=['ldacm_data_volumeDefinitionsAccu1'])
    for error in ERROR_CLASSES:
        response = send_command(init, 'getErrorState', error, return_parameters=['pendingErrors'])
        value = response['pendingErrors']
        ERROR_LIST.append(value)

    # 1024 (int) --> 400 (hex) --> '04 00' (hex string) --> '00 04' (LSB stirng)    # Conversion example
    '00 0A'

    # Generate history log entries
    for entry in range(AMOUNT_OF_HISTORY_LOG_ENTRIES):
        send_command(init, 'triggerHistoryLogDatasetGeneration')

    check_roles(init, mode, activate_sitp, role)

    # Read datasets
    OUT_OF_HISTORY_LOG_DATA.clear()
    ERROR_LIST.clear()

    forward_volume_data = send_command(init, 'Get_ldacm_data_volumeDefinitionsAccu1',
                                       return_parameters=['ldacm_data_volumeDefinitionsAccu1'])
    forward_value = forward_volume_data['ldacm_data_volumeDefinitionsAccu1']

    backward_volume_data = send_command(init, 'Get_ldacm_data_volumeDefinitionsAccu2',
                                        return_parameters=['ldacm_data_volumeDefinitionsAccu2'])
    backward_value = backward_volume_data['ldacm_data_volumeDefinitionsAccu2']

    for error in ERROR_CLASSES:
        response = send_command(init, 'getErrorState', error, return_parameters=['pendingErrors'])
        value = response['pendingErrors']
        ERROR_LIST.append(value)

    OUT_OF_HISTORY_LOG_DATA.append(ERROR_LIST)

    # TODO: Read maximum forward flowrate.
    # TODO: Read current flowrate.
    # TODO : Add rest of data to LIST_OF_ALL_DATA_TYPES after commands available

    LIST_OF_ALL_DATA_TYPES = list(chain(forward_value, backward_value, ERROR_LIST))

    # Check content of history log
    HISTORY_LOG_DATA.clear()
    response = send_command(init, 'readHistoryLog', return_parameters=['dataSet'])
    contents = response['dataset']
    HISTORY_LOG_DATA.append(contents)

    # TODO: Finish compare algorithm
    # Compare data
    for data in LIST_OF_ALL_DATA_TYPES:
        if data in HISTORY_LOG_DATA:
            pass
        else:
            assert "Values in history log and out of it are not equal"

    # Clear history log
    send_command(init, 'deleteHistoryLog')

    # POSTCONDITIONS

    postconditions(init, set_operation_mode)


@pytest.mark.test_id('cd96d7b4-fbe4-49f0-b0a2-c14aa26d1211')
@pytest.mark.req_ids(['NoReq'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('26.08.2021')
@allure.title('Deleting history log by different commands')
@allure.description('''This test checks if history log is deleted after using 
                        one of the commands that should cause history log deletion.
                        These are: 'Set_ldacm_data_outputVolumeDecimalPlace', 
                        'configureDigitHighlighting',''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
@pytest.mark.parametrize('role', ['REP, LAB, TES, UTL'])
def test_history_log_deleting_log_by_different_commands(init, mode, role, set_operation_mode, activate_sitp, selector):
    # PRECONDITIONS

    preconditions(init, set_operation_mode, mode, selector)

    # Generate some flow to make sure logs are not empty
    send_command(init, 'Set_ldacm_data_volumeDefinitionsAccu0', SUM_VOLUME)

    # TEST STEPS

    check_roles(init, mode, activate_sitp, role)

    # Generate log
    send_command(init, 'triggerHistoryLogDatasetGeneration')

    # Read history log content
    response = send_command(init, 'readHistoryLog', parameters='00', return_parameters=['dataSet'])
    check_if_empty = response['dataset']
    LIST_OF_ENTRIES.append(check_if_empty)
    if LIST_OF_ENTRIES[0] == '0x0':
        assert "History log should not be empty"
    else:
        pass

    # TODO: Steps 5-8 are unclear

    # POSTCONDITIONS

    postconditions(init, set_operation_mode)


@pytest.mark.test_id('cd96d7b4-fbe4-49f0-b0a2-c14aa26d1211')
@pytest.mark.req_ids(['NoReq'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('26.08.2021')
@allure.title('History log after reset')
@allure.description('''This test checks if history log is kept intact after resetting the meter.''')
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK, MeterMode.PRODUCTION])
def test_history_log_after_reset(init, mode, set_operation_mode, selector):
    # PRECONDITIONS

    preconditions(init, set_operation_mode, mode, selector)

    # TEST STEPS

    # Generate 100 logs with simulation in between
    send_command(init, 'EnableUltrasonicSimulation', '00')  # Uncompleted command.
    for log in range(100):
        send_command(init, 'triggerHistoryLogDatasetGeneration')

    # Save history log content
    history_log_content = send_command(init, 'readHistoryLog', parameters='00', return_parameters=['dataSet'])

    # Save the number of entries in log
    history_log_nr_of_entries = send_command(init, 'getHistoryLogInfo', '00', return_parameters=['nrOfEntries'])

    # Save the number of possible entries in log
    history_log_nr_of_possible_entries = send_command(init, 'getHistoryLogInfo', '00',
                                                      return_parameters=['nrOfPossibleEntries'])

    # Reset the meter
    # TODO: Wait for command

    # Get history log content, number of entries and number of possible entries
    after_reset_content = send_command(init, 'readHistoryLog', parameters='00', return_parameters=['dataSet'])
    after_reset_nr_of_entries = send_command(init, 'getHistoryLogInfo', '00', return_parameters=['nrOfEntries'])
    after_reset_nr_of_possible_entries = send_command(init, 'getHistoryLogInfo', '00',
                                                      return_parameters=['nrOfPossibleEntries'])

    # POSTCONDITIONS

    postconditions(init, set_operation_mode)
    assert history_log_content == after_reset_content, "Content in history log is not equal"
    assert history_log_nr_of_entries == after_reset_nr_of_entries, "Number of entries is not equal"
    assert history_log_nr_of_possible_entries == after_reset_nr_of_possible_entries,"Number of possible entries " \
                                                                                    "is not equal"
