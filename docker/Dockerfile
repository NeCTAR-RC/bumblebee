FROM debian:bullseye

ADD requirements.txt /app/requirements.txt

RUN set -ex \
    && apt-get -y update \
    && apt-get -y install apache2 libapache2-mod-wsgi-py3 python3-venv python3-pip python3-mysqldb \
    && python3 -m venv --system-site-packages /env \
    && /env/bin/pip install --upgrade pip \
    && /env/bin/pip install --no-cache-dir -r /app/requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

ADD guacamole /app/guacamole
ADD researcher_desktop /app/researcher_desktop
ADD researcher_workspace /app/researcher_workspace
ADD vm_manager /app/vm_manager

WORKDIR /app
ENV VIRTUAL_ENV /env
ENV PATH /env/bin:$PATH
ENV PYTHONPATH /app
ENV DJANGO_SETTINGS_MODULE researcher_workspace.settings

COPY docker/docker-*.sh /
COPY docker/apache.conf /etc/apache2/sites-available/000-default.conf

RUN chmod u+x /docker-*.sh
RUN echo "ServerName localhost" >> /etc/apache2/apache2.conf
RUN django-admin collectstatic --noinput && django-admin compress --force

EXPOSE 80

CMD ["/docker-run-bumblebee.sh"]
