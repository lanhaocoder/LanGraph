#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 16 00:19:13 2018

@author: lanhao
"""
import os
import time
import threading
import re
import pickle

INPUT_FILE_WITH_STACK="langraph.dat"
OUTPUT_FILE="langraph.out.txt"
TRACE_FILE="langraph.trace"

NAME_OFFSET=0
NAME_START=0
NAME_SIZE=16
NAME_END=NAME_START+NAME_SIZE
TID_OFFSET=1
TID_START=NAME_END+TID_OFFSET
TID_SIZE=7
TID_END=TID_START+TID_SIZE
PID_OFFSET=2
PID_START=TID_END+PID_OFFSET
PID_SIZE=7
PID_END=PID_START+PID_SIZE
CPU_OFFSET=3
CPU_START=PID_END+CPU_OFFSET
CPU_SIZE=3
CPU_END=CPU_START+CPU_SIZE
STATE_OFFSET=2
STATE_START=CPU_END+STATE_OFFSET
STATE_SIZE=5
STATE_END=STATE_START+STATE_SIZE

def save_variable(v,filename):
    f=open(filename,'wb')
    pickle.dump(v,f)
    f.close()
    return filename

def load_variavle(filename):
    f=open(filename,'rb')
    v=pickle.load(f)
    f.close()
    return v

def read_input(filename):
    f=open(filename,'r')
    lines = f.readlines()
    f.close()
    data=list()
    for line in lines:
        if "[LOST]" in line:
            del data
            data = list()
        data.append(line)
    return data

STACK_NAME_INDEX = 1
STACK_ADDR_INDEX = 2
def stack_handle(line, priv):
    key_word = line.split()
    priv.append([key_word[STACK_NAME_INDEX], key_word[STACK_ADDR_INDEX]])

def null_init(line):
    return []

def null_handle(line, priv):
    return

event_type = {
    "sched_kthread_stop"               : [null_init, null_handle],
    "sched_kthread_stop_ret"           : [null_init, null_handle],
    "sched_kthread_work_execute_end"   : [null_init, null_handle],
    "sched_kthread_work_execute_start" : [null_init, null_handle],
    "sched_kthread_work_queue_work"    : [null_init, null_handle],
    "sched_migrate_task"               : [null_init, null_handle],
    "sched_move_numa"                  : [null_init, null_handle],
    "sched_pi_setprio"                 : [null_init, null_handle],
    "sched_process_exec"               : [null_init, null_handle],
    "sched_process_exit"               : [null_init, null_handle],
    "sched_process_fork"               : [null_init, null_handle],
    "sched_process_free"               : [null_init, null_handle],
    "sched_process_hang"               : [null_init, null_handle],
    "sched_process_wait"               : [null_init, null_handle],
    "sched_stat_blocked"               : [null_init, null_handle],
    "sched_stat_iowait"                : [null_init, null_handle],
    "sched_stat_runtime"               : [null_init, null_handle],
    "sched_stat_sleep"                 : [null_init, null_handle],
    "sched_stat_wait"                  : [null_init, null_handle],
    "sched_stick_numa"                 : [null_init, null_handle],
    "sched_swap_numa"                  : [null_init, null_handle],
    "sched_switch"                     : [null_init, null_handle],
    "sched_wait_task"                  : [null_init, null_handle],
    "sched_wake_idle_without_ipi"      : [null_init, null_handle],
    "sched_wakeup"                     : [null_init, null_handle],
    "sched_wakeup_new"                 : [null_init, null_handle],
    "sched_waking"                     : [null_init, null_handle],
    "<stack trace>"                    : [null_init, stack_handle],
    "<user stack trace>"               : [null_init, stack_handle]
}

TRACE_RETURN_TRUE=0
TRACE_RETURN_FALSE=1
TRACE_RETURN_STACK=2
"<...>-154717  ( 154717) [000] d.... 27117.357065: sched_stat_runtime: "
class trace_event:
    def __init__(self, line=""):
        self.available = TRACE_RETURN_TRUE
        if line.__len__() == 0:
            self.available = TRACE_RETURN_FALSE
            return
        if line[0] == '#':
            self.available = TRACE_RETURN_FALSE
            return
        if line[0:4] == ' => ':
            if len(line.split()) == 3:
                self.available = TRACE_RETURN_STACK
                return
            else:
                self.available = TRACE_RETURN_FALSE
                return
        self.name  = line[ NAME_START: NAME_END].strip()
        self.tid   = line[  TID_START:  TID_END].strip()
        self.pid   = line[  PID_START:  PID_END].strip()
        self.cpu   = int(line[  CPU_START:  CPU_END].strip())
        self.state = line[STATE_START:STATE_END].strip()
        key_word = line[TID_START:-1].split(':')
        self.timestamp = float(key_word[0].split()[-1])
        self.event_type_name = key_word[1].strip()
        if self.event_type_name in event_type:
            [init_op, handle_op] = event_type[self.event_type_name]
            self.event_type_priv = init_op(line)
        else:
            self.event_type_priv = list()
    def get_available(self):
        return self.available
    def handle(self, line):
        if self.available != TRACE_RETURN_TRUE:
            return
        if self.event_type_name in event_type:
            [init_op, handle_op] = event_type[self.event_type_name]
            handle_op(line, self.event_type_priv)

class task_event:
    def __init__(self, timestamp, pid):
        self.pid = pid
        self.timestamp = timestamp
        self.latency = 0
    def set_end_timestamp(self, timestamp):
        self.latency = timestamp - self.timestamp

def get_data(data):
    data_len = len(data)
    if data_len == 0:
        return
    last_te = trace_event(data[0])
    te_list=list()
    for i in range(0, data_len):
        line = data[i]
        #print(line)
        te = trace_event(line)
        if te.get_available() == TRACE_RETURN_FALSE:
            continue
        if te.get_available() == TRACE_RETURN_STACK:
            if last_te.get_available() == TRACE_RETURN_TRUE:
                last_te.handle(line)
                continue
            continue
        last_te = te
        te_list.append(te)
    return te_list

if __name__ == '__main__':
    data = read_input(INPUT_FILE_WITH_STACK)
    te_list=get_data(data)