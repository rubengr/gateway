# Integration Tests

The testing toolbox uses the following environment variables to connect to the
tester and target gateways.  The tests also expects the event_observer and
syslog_receiver (debugging only) plugins to be installed on the tester gateway.

```
OPENMOTICS_OBSERVER_AUTH=username:password
OPENMOTICS_OBSERVER_HOST=gateway-tester.qa.openmotics.com
OPENMOTICS_TARGET_AUTH=username:password
OPENMOTICS_TARGET_HOST=gateway-testee-debian.qa.openmotics.com
```

- quick smoketest

```
pytest testing/cicd/tests --disable-warnings --hypothesis-profile once -m smoke
```

- full testrun

```
pytest testing/cicd/tests --disable-warnings --log-cli-level=INFO -m 'smoke or slow'
```

## Target gateway deployment

The test system is also deployed slightly differently.

- syslog to the plugin running on the tester system

```
rsync rsyslog/99-openmotics-tester.conf target:/etc/rsyslog.d/
ssh target -- systemctl restart rsyslog
```

- run gateway services using systemd

```
rsync -a systemd/ target:/etc/systemd/system/
```

```
systemctl stop supervisor
systemctl disable supervisor

systemctl daemon-reload

systemctl enable openmotics
systemctl enable openmotics-led
systemctl enable openmotics-vpn
systemctl enable openmotics-watchdog

systemctl start openmotics
systemctl start openmotics-led
systemctl start openmotics-vpn
systemctl start openmotics-watchdog
```
