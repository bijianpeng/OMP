#!/bin/bash
# Author:
# Description:
PARENT_DIR=$(cd -P -- $(dirname -- "$0") && pwd -P)

APP_NAME="monitor_agent_exporter"
LOGFILE=$PARENT_DIR/log/app.log
CONFIG_FILE=$PARENT_DIR/conf/config.yaml
CURRENT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
THIS_SCRIPT="${CURRENT_DIR}/$(basename $0)"

sed -i -e "s#\${PROJECT_PATH}#$PARENT_DIR#g" $CONFIG_FILE

start() {
  status >/dev/null
  if [[ $? -eq 0 ]]; then
    echo  "${APP_NAME} [running]"
    exit 0
  else
    cd $PARENT_DIR
    rm -rf $PARENT_DIR/lib/executions/_*
    exec $PARENT_DIR/monitor_agent_exporter >/dev/null 2>&1 &
    sleep 2

    pid_port=`ps aux | grep monitor_agent_exporter | grep -v grep`
    if [ ! -n "${pid_port}" ];then
       echo  "启动失败 ${APP_NAME} [not running] start failed"
       exit 1
    fi;
    status
  fi;
}

stop() {
    ps -ef | grep monitor_agent_exporter | grep -v grep | awk -F ' ' '{print $2}' | xargs kill -9
    status
    if [[ $? -eq 11 ]]; then
      return 0
    fi
}

status() {
  pid_info=`ps aux | grep monitor_agent_exporter | grep -v grep`
  if [ ! -n "${pid_info}" ];then
     echo  "${APP_NAME} [not running]"
     return 11
  else
     echo  "${APP_NAME} [running]"
     return 0
  fi;
}

alive() {
  status
  if [[ $? -eq 0 ]]; then
    exit 0
  else
    start
  fi
}


init() {
  if [[ `id -u` -ne 0 ]]; then
    sudo -n 'whoami' &>/dev/null
    if [[ $? -ne 0 ]]; then
      exit 0
    fi
  fi
  crontab -l 2>/dev/null | grep ${THIS_SCRIPT} >/dev/null
  if [[ $? -eq 0 ]]; then
    exit 0
  else
    crontab -l 2>/dev/null >/tmp/omp_agent_monitor_cron
    grep ${THIS_SCRIPT} /tmp/omp_agent_monitor_cron
    if [[ $? -eq 0 ]]; then
      exit 0
    else
      echo "*/5 * * * * bash ${THIS_SCRIPT} alive &>/dev/null" >> /tmp/omp_agent_monitor_cron
      crontab /tmp/omp_agent_monitor_cron && rm -f /tmp/omp_agent_monitor_cron
    fi
  fi
  exit 0
}

case $1 in
    start) start ;;
    stop) stop ;;
    restart)
       stop
       start
       ;;
    status)
       status
       ;;
    alive)
       alive
       ;;
    init)
       init
       ;;
    *) echo "usage: $0 [start|stop|status]"
       ;;
esac
