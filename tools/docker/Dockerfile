FROM debian:9

COPY requirements.txt /tmp/

RUN apt-get update && apt-get -y upgrade && \
    apt-get install -y python2.7 python-pip procps supervisor libdbus-1-dev libglib2.0-dev vim && \
    pip install pyserial==2.4 dbus-python==1.2.8 pyopenssl==18.0.0 simplejson==3.16.0 && \
    pip install -r /tmp/requirements.txt

COPY src.tgz files/openmotics.conf files/https.crt files/https.key files/supervisor-*.conf files/entrypoint.sh /tmp/

RUN mkdir -p /opt/openmotics && \
    cd /tmp/ && tar xzf src.tgz && mv src /opt/openmotics/python && \
    mkdir /opt/openmotics/etc && mkdir /opt/openmotics/static && \
    mv /tmp/openmotics.conf /tmp/https.crt /tmp/https.key /opt/openmotics/etc/ && \
    mv /tmp/supervisor-*.conf /etc/supervisor/conf.d && \
    mv /tmp/entrypoint.sh /entrypoint.sh

CMD [ "/entrypoint.sh" ]
