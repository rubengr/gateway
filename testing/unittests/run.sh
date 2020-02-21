#!/bin/bash -e
export PYTHONPATH=$PYTHONPATH:`pwd`/../../src

echo "Running master api tests"
python2 master_tests/master_api_tests.py

echo "Running master command tests"
python2 master_tests/master_command_tests.py

echo "Running master communicator tests"
python2 master_tests/master_communicator_tests.py

echo "Running outputs tests"
python2 master_tests/outputs_tests.py

echo "Running inputs tests"
python2 master_tests/inputs_tests.py

echo "Running passthrough tests"
python2 master_tests/passthrough_tests.py

echo "Running eeprom controller tests"
python2 master_tests/eeprom_controller_tests.py

echo "Running eeprom extension tests"
python2 master_tests/eeprom_extension_tests.py

echo "Running users tests"
python2 gateway_tests/users_tests.py

echo "Running scheduling tests"
python2 gateway_tests/scheduling_tests.py

echo "Running power controller tests"
python2 power_tests/power_controller_tests.py

echo "Running power communicator tests"
python2 power_tests/power_communicator_tests.py

echo "Running time keeper tests"
python2 power_tests/time_keeper_tests.py

echo "Running plugin base tests"
python2 plugins_tests/base_tests.py

echo "Running plugin interfaces tests"
python2 plugins_tests/interfaces_tests.py

echo "Running pulse counter controller tests"
python2 gateway_tests/pulses_tests.py

echo "Running classic controller tests"
python2 gateway/hal/master_controller_classic_test.py

echo "Running core controller tests"
python2 gateway/hal/master_controller_core_test.py

echo "Running observer tests"
python2 gateway/observer_test.py

echo "Running Core uCAN tests"
python2 master_core_tests/ucan_communicator_tests.py

echo "Running Core memory file tests"
python2 master_core_tests/memory_file_tests.py

echo "Running Core api field tests"
python2 master_core_tests/api_field_tests.py

echo "running Core communicator tests"
python2 master_core_tests/core_communicator_tests.py

echo "Running metrics tests"
python2 gateway_tests/metrics_tests.py
