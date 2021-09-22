import pytest
import allure
from time import sleep

from support.hydrus2.consumption_manager import ConsumptionManager
from support.hydrus2.communication import send_command
from support.meter_types import OperationMode, MeterMode, MeterOperation, UltrasonicSimulationMode
from tests.conftest import ultrasonic_simulation
from support.hydrus2.commands import disable_ultrasonic_simulation

# **********************************
# Global parameters and dictionaries
# **********************************


CONSUMER_ENABLE = {
    'Tx': '01 00 00',
    'Rx': '00 01 00',
    'Passive': '00 00 01',
    'All': '01 01 01',
    'Disable': '00 00 00'
}
REGENERATION_TIME = 62
NO_ERRORS = '26 00 00 00 00 00 00'


# **********************************
# Local Functions
# **********************************


# supervisor_name: 'mbus' / 'irda' / 'ext_mem'
# consumers:
# mbus: 'tx' / 'rx' / 'passive'
# irda: 'tx' / 'rx'
# ext_mem: 'rw'
def configure_consumption_manager(init, set_operation_mode, get_operation_mode, activate_sitp, configuration,
                                  supervisor_name):
    # Initialize Consumption manager object
    consumption_manager = ConsumptionManager(init)

    # Disable all supervisors
    registered_supervisors = consumption_manager.supervisors()
    for supervisor in registered_supervisors:
        supervisor.enabled = False

    # Enable supervisor
    consumption_manager.supervisor(supervisor_name).enabled = True

    # Chose consumer
    supervisor = consumption_manager.supervisor(supervisor_name)

    # Disable all consumers
    registered_consumers = supervisor.consumers()
    for consumer in registered_consumers:
        consumer.enabled = False

    # Enable needed consumer
    if configuration["switch"] == 'all':
        for consumer in registered_consumers:
            consumer.enabled = True
    elif configuration["switch"] == 'none':
        for consumer in registered_consumers:
            consumer.enabled = False
    else:
        supervisor.consumer(configuration["switch"]).enabled = True

    # Configure settings
    supervisor.quantifier = 0
    supervisor.regeneration_value = configuration["regeneration"]
    if configuration["over_load"] is not None:
        supervisor.threshold_overload = configuration["over_load"]
    supervisor.threshold_underload = configuration["under_load"]

    # Change to desired operation mode
    set_operation_mode(OperationMode(configuration['mode'], MeterOperation.NORMAL))
    returned_mode = get_operation_mode()
    if returned_mode.mode != configuration['mode'] and returned_mode.operation != MeterOperation.NORMAL:
        raise Exception(f'Pre-conditions not met! Meter is not in {configuration["mode"]} mode')
    if configuration['role'] is not None:
        activate_sitp(configuration['role'])


def create_low_medium_error(init, activate_sitp, ultrasonic_simulation, role):
    low_limit_medium_temp = '0E 01'  # 27.0'
    high_limit_medium_temp = '54 01'  # 34.0'

    activate_sitp('REP')

    # set low limit to 27.0'
    send_command(init, 'Set_nldacm_data_errorHandling_threshold_freezingRisk', low_limit_medium_temp)
    # set high limit to 34.0'
    send_command(init, 'Set_nldacm_data_errorHandling_threshold_highMediumTemperature', high_limit_medium_temp)

    # start simulation (only for set medium temp = 10.0 and create low_medium_error which will be written in event log)
    ultrasonic_simulation(simulation_mode=UltrasonicSimulationMode.NORMAL, phase_shift_diff=10240,
                          medium_temperature=100, resonator_calibration=False, time_difference_1us=4000,
                          sonic_speed_correction=19665)

    # reset error
    send_command(init, 'resetAllPendingErrors')

    sleep(120)

    # stop simulation
    disable_ultrasonic_simulation(init)

    activate_sitp(role)


def int_to_hex_string(integer: int, num_bytes: int) -> str:
    return integer.to_bytes(num_bytes, 'little').hex().upper()


def hex_string_to_int(lsb_hex_string):
    int_value = int("".join(lsb_hex_string.split()[::-1]), 16)
    return int_value


def allure_attach(configuration):
    allure.attach(f"""
                  <h2>Test result</h2>
                  <table style="width:100%">
                    <tr>
                      <th>Operation mode:</th>
                      <th>Role:</th>
                      <th>Enabled Consumer:</th>
                      <th>configured regeneration:</th>
                      <th>configured overload:</th>
                      <th>configured underload:</th>
                    </tr>
                    <tr align="center">
                      <td>{configuration['mode']}</td>
                      <td>{configuration['role']}</td>
                      <td>{configuration['switch']}</td>
                      <td>{configuration['regeneration']}</td>
                      <td>{configuration['over_load']}</td>
                      <td>{configuration['under_load']}</td>
                    </tr>
                  </table>
                  """,
                  'Test result',
                  allure.attachment_type.HTML)


@pytest.mark.test_id('2480678c-a9d8-4fb7-9474-f9c0bdcf0887')
@pytest.mark.req_ids(['F362', 'F461', 'F462', 'F460'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('20.09.2021')
@allure.title('Triggering error')
@allure.description('The consumption manager shall trigger an error if consumption budget is risen by any of the '
                    'consumers: LBUS, IRDA. After exceeding the threshold communication via consumer should be blocked.'
                    'This test also indirectly checks if flow sensor has consumption manager implemented.')
@pytest.mark.parametrize('supervisor', ['lbus', 'irda'])
@pytest.mark.parametrize('switch', ['tx', 'rx', 'passive'])
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK])
@pytest.mark.parametrize('role', [None])
def test_consumption_manager_trigger_error(init, mode, role, set_operation_mode, get_operation_mode, activate_sitp,
                                           supervisor, switch):
    # PRE-CONDITIONS
    # Configure consumption manager and set operation mode
    configuration = {
        'mode': mode,
        'role': role,
        'regeneration': 255,
        'switch': switch,
        'over_load': 100,  # Above this threshold communication is blocked
        'under_load': 1  # Below this threshold communication is unlocked
    }

    configure_consumption_manager(init, set_operation_mode, get_operation_mode, activate_sitp, configuration,
                                  supervisor)

    # Read error state
    initial_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]

    # TEST STEPS
    # Generate less then X traffic for the consumer ID. Assume that this command uses 20 bytes.
    for _ in range(3):
        send_command(init, 'LoopBackGivenBytes', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00')

    # Read error state for 60 bytes
    check_60_bytes = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]

    # Try to communicate via consumer
    send_command(init, 'LoopBackGivenBytes', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00')

    # Check if communication is possible
    com_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]
    check_80_bytes = bin(int("com_error_state", 16))[2:]

    # Generate more bytes to fill consumers accu to 100
    send_command(init, 'LoopBackGivenBytes', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00')

    # Read error sate for 100 bytes
    com_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]

    # Check if communication is possible
    check_100_bytes = bin(int("com_error_state", 16))[2:]

    # Wait as much time as it is needed for consumption manager to regenerate so that accu value is less then X
    sleep(60)

    # Read error state after regeneration
    regen_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]

    # POST-CONDITION
    allure_attach(configuration)

    # TODO: Reset customer accus - command is required, above new config was used for the same step

    # Go to production mode
    set_operation_mode(OperationMode(MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # Reset meter errors
    send_command(init, 'resetAllPendingErrors')

    # TODO: pytanie, czy oba sposoby sprawdzania poniżej errorów zadziałają?
    # Check if any pending errors exists
    assert initial_error_state == NO_ERRORS
    assert check_60_bytes == NO_ERRORS
    assert check_80_bytes[22] == '0'
    assert check_100_bytes[22] == '1'
    assert regen_error_state == NO_ERRORS


@pytest.mark.test_id('9548e275-0516-4ab8-a34d-f419529aa220')
@pytest.mark.req_ids(['F456'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('20.09.2021')
@allure.title('L-Bus cyclic communication')
@allure.description('There should be such configuration for L-Bus possible that cyclic communications requests of INT9 '
                    'are possible without an error')
@pytest.mark.parametrize('supervisor', ['lbus'])
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK])
@pytest.mark.parametrize('role', [None])
def test_consumption_manager_lbus_communication(init, mode, role, set_operation_mode, get_operation_mode,
                                                activate_sitp, supervisor):
    # PRE-CONDITIONS
    # Configure consumption manager and set operation mode
    configuration = {
        'mode': mode,
        'role': role,
        'regeneration': 255,
        'switch': ['tx', 'rx', 'passive'],
        'over_load': 100,  # Above this threshold communication is blocked
        'under_load': 1  # Below this threshold communication is unlocked
    }

    configure_consumption_manager(init, set_operation_mode, get_operation_mode, activate_sitp, configuration,
                                  supervisor)

    # Read error state
    initial_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]

    # TEST STEPS:
    # Try to communicate with int9 through L-Bus once every period for test_time (e.g. test_time=5min, period=30sec)
    for _ in range(10):
        send_command(init, 'LoopBackGivenBytes', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00')
        sleep(30)

    error_state_after_test_time = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])[
        "pendingErrors"]

    # POST-CONDITIONS
    allure_attach(configuration)

    # TODO: Reset customer accus - command is required

    # Go to production mode
    set_operation_mode(OperationMode(MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # Check if any pending errors exists
    assert initial_error_state == NO_ERRORS
    assert error_state_after_test_time == NO_ERRORS


@pytest.mark.test_id('7e121594-8da4-4ea6-a1e1-1e074d3932bc')
@pytest.mark.req_ids(['F457'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('20.09.2021')
@allure.title('IrDA log readout')
@allure.description("There should be such configuration that makes it possible to read out all the log contents "
                    "in 'one go', this means one after another. Logs to be tested are: MetrologicalLog, HistoryLog, "
                    "Eventlog, Quality Log and Exception recorder.")
@pytest.mark.parametrize('supervisor', ['irda'])
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK])
@pytest.mark.parametrize('role', [None])
def test_consumption_manager_irda_log_readout(init, mode, role, set_operation_mode, get_operation_mode, activate_sitp,
                                              supervisor, open_metrological_log):
    # PRE-CONDITIONS
    # Configure consumption manager and set operation mode
    configuration = {
        'mode': mode,
        'role': role,
        'regeneration': 255,
        'switch': ['tx', 'rx'],
        'over_load': 100,  # Above this threshold communication is blocked
        'under_load': 1  # Below this threshold communication is unlocked
    }

    configure_consumption_manager(init, set_operation_mode, get_operation_mode, activate_sitp, configuration,
                                  supervisor)

    # Read error state
    initial_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]

    # TEST STEPS
    # FILLING ALL THE LOGS
    # History log
    send_command(init, "controlHistoryLog", "01")
    history_log_max_entries = send_command(init, "getHistoryLogInfo ",
                                           return_parameters=['nrOfPossibleEntries'])['nrOfPossibleEntries']
    history_log_max_entries = hex_string_to_int(history_log_max_entries)
    for _ in range(history_log_max_entries):
        send_command(init, 'triggerHistoryLogDatasetGeneration')
    history_log_entries = send_command(init, "getHistoryLogInfo ",
                                       return_parameters=['nrOfEntries'])['nrOfEntries']
    history_log_entries = hex_string_to_int(history_log_entries)

    # Metrological log
    open_metrological_log('REP')
    metrological_log_max_entries = 20
    for _ in range(metrological_log_max_entries):
        send_command(init, 'Set_ldacm_data_volumeDefinitionsMetrologicalAccuSelection', '00')
    metrological_log_entries = send_command(init, 'ReadLogMetrological', '00',
                                            return_parameters=['availableNumberOfDatasets'])
    metrological_log_entries = hex_string_to_int(metrological_log_entries['availableNumberOfDatasets'])

    # Event log
    event_log_max_entries = 255
    # TODO: how can I generate entry faster then 2 min?
    for _ in range(event_log_max_entries):
        # generate log
        create_low_medium_error(init, activate_sitp, ultrasonic_simulation, 'REP')
    event_log_entries = send_command(init, 'ReadEventLogRingBuffer', '00',
                                     return_parameters=['availableNumberOfDatasets'])['availableNumberOfDatasets']
    event_log_entries = hex_string_to_int(event_log_entries)

    # READING ALL THE LOGS
    # History log
    history_log_read = []
    for iteration in range(history_log_entries):
        entry = send_command(init, 'readHistoryLog', int_to_hex_string(iteration, 2) + ' 01',
                             return_parameters=['dataSet'])['dataSet']
        history_log_read.append(entry)

    # Metrological log
    metrological_log_read = []
    for iteration in range(metrological_log_entries):
        entry = send_command(init, 'ReadLogMetrological ', int_to_hex_string(iteration, 1),
                             return_parameters=['timeOfChangeAsTypeFFormat'])['timeOfChangeAsTypeFFormat']
        metrological_log_read.append(entry)

    # Event log
    event_log_read = []
    for iteration in range(event_log_entries):
        entry = send_command(init, 'ReadEventLogRingBuffer', int_to_hex_string(iteration, 1),
                             return_parameters=['dateTime'])['dateTime']
        event_log_read.append(entry)

    # Exception recorder
    exceptions = send_command(init, 'ReadExceptionRecorder',
                              return_parameters=['allocationConflict',
                                                 'clockInitError',
                                                 'unexpectedIsrExecution',
                                                 'osIntervalOutOfRange',
                                                 'osProcessIdNotAvailable',
                                                 'osQueueIsFull',
                                                 'osEventIdNotAvailable',
                                                 'resetOccured',
                                                 'lastResetSource',
                                                 'synchronicityWatchdogSourceByte1',
                                                 'synchronicityWatchdogSourceByte2',
                                                 'faultyMeasCommunications',
                                                 'startUp_faultyMeasCommunications',
                                                 'metrologicalLogCorrupt',
                                                 'metrologicalAccessMonitoringCorrupt',
                                                 'ramIntegrityCorrupt',
                                                 'romIntegrityCorrupt',
                                                 'measIntegrityCorrupt',
                                                 'globalIntegrityError',
                                                 'faultyMeasBatVoltage',
                                                 'watchdogTimeout',
                                                 'faultyRadioCommunications',
                                                 'measProcessorBlackout',
                                                 'measProcessorReset',
                                                 'radioProcessorReset',
                                                 'backupRestored',
                                                 'backupRestorationFailed',
                                                 'corruptRamCrcSegments',
                                                 'corruptRomCrcSegments',
                                                 'faultyExternalMemoryCommunication',
                                                 'lastFaultyExternalMemoryCommunicationSource'])

    # POST-CONDITIONS
    allure.attach(f"""
                                                <h2>Test result</h2>
                                                <table style="width:100%">
                                                  <tr>
                                                    <th>[Expected] History log</th>
                                                    <th>[Result] History log</th>
                                                    <th>[Expected] Metrological log</th>
                                                    <th>[Result] Metrological log</th>
                                                    <th>[Expected] Event log</th>
                                                    <th>[Result] Event log</th>
                                                    <th>[Expected] Quality log</th>
                                                    <th>[Result] Quality log</th>
                                                    <th>[Expected] Exception recorder</th>
                                                    <th>[Result] Exception recorder</th>
                                                  </tr>
                                                  <tr align="center">
                                                    <td>{history_log_max_entries}</td>
                                                    <td>{len(history_log_read)}</td>
                                                    <td>{metrological_log_max_entries}</td>
                                                    <td>{len(metrological_log_read)}</td>
                                                    <td>{event_log_max_entries}</td>
                                                    <td>{len(metrological_log_read)}</td>
                                                    <td>{'quality dummy'}</td>
                                                    <td>{'quality dummu'}</td>
                                                    <td>{31}</td>
                                                    <td>{len(exceptions)}</td>
                                                  </tr>
                                                </table>
                                                """,
                  'Test result',
                  allure.attachment_type.HTML)

    # Go to production mode
    set_operation_mode(OperationMode(MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # TODO: delete metrological log contents

    # Check if any pending errors exists
    assert initial_error_state == NO_ERRORS
    assert history_log_max_entries == len(history_log_read)
    assert metrological_log_max_entries == len(metrological_log_read)
    assert event_log_max_entries == len(metrological_log_read)
    assert 31 == len(exceptions)


@pytest.mark.test_id('e16dfa43-c279-486b-ac17-e822d458eedd')
@pytest.mark.req_ids(['NoReq'])
@pytest.mark.creator('Grzegorz Szymanski')
@pytest.mark.creation_date('20.09.2021')
@allure.title('Consumption manager after reset')
@allure.description('This test checks if after consumption manager block the comunication via active interface is '
                    'blocked even if reset is done.')
@pytest.mark.parametrize('supervisor', ['lbus', 'irda'])
@pytest.mark.parametrize('mode', [MeterMode.FIELD_FALLBACK])
@pytest.mark.parametrize('role', [None])
def test_consumption_manager_after_reset(init, mode, role, set_operation_mode, get_operation_mode, activate_sitp,
                                         supervisor):
    # PRE-CONDITIONS
    # Configure consumption manager and set operation mode
    configuration = {
        'mode': mode,
        'role': role,
        'regeneration': 255,
        'switch': ['tx', 'rx', 'passive'],
        'over_load': 100,  # Above this threshold communication is blocked
        'under_load': 1  # Below this threshold communication is unlocked
    }

    configure_consumption_manager(init, set_operation_mode, get_operation_mode, activate_sitp, configuration,
                                  supervisor)

    # Read error state
    initial_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]

    # TEST STEPS
    # Configure consumption manager over_load threshold to value X. Assume that this command uses 20 bytes.
    for _ in range(5):
        send_command(init, 'LoopBackGivenBytes', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00')

    # Read error state for 100 bytes
    second_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]

    # Reset all errors
    send_command(init, 'resetAllPendingErrors')

    # Try to communicate via consumer
    send_command(init, 'LoopBackGivenBytes', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00')

    # Read error state
    third_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]

    # Reset the meter
    send_command(init, 'LowLevelPowerAndReset', parameters='06')

    # Try to communicate via consumer
    send_command(init, 'LoopBackGivenBytes', '00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00')

    # Check if communication is possible
    com_error_state = send_command(init, 'getErrorState', return_parameters=["pendingErrors"])["pendingErrors"]
    hex_to_bin = bin(int("com_error_state", 16))[2:]

    # POST-CONDITIONS
    allure_attach(configuration)

    # Go to production mode
    set_operation_mode(OperationMode(MeterMode.PRODUCTION, operation=MeterOperation.NORMAL))

    # TODO: delete metrological log contents

    # Check if any pending errors exists
    assert initial_error_state == NO_ERRORS
    assert second_error_state != NO_ERRORS
    assert third_error_state != NO_ERRORS
    assert hex_to_bin[22] == '1'

    # To niżej niech wisi żebym nie zgubił XD

    # EnableDisableLBus
    # Set_ldacm_data_consumptionManagerGeneralDynamicConsumptionEnable
    # Set_ldacm_data_consumptionManagerGeneralSupervisorEnable
    # Set_ldacm_data_consumptionManagerConsumerConsumerEnable
    # isMetrologicalLogEnabled, controlMetrologicalLog
    # Set_ldacm_data_consumptionManagerGeneralSupervisorQuantifier
    # configure_consumption_manager
