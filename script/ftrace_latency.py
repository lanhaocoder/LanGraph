#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 16 00:19:13 2018

@author: lanhao
"""
import os
import urllib.request
import time
import threading
import re
import pickle

INPUT_FILE_WITH_STACK="trace.data.split.txt"
OUTPUT_FILE="trace.dat.any.txt"
INPUT_FILE="trace.dat.txt"

HARD_IRQ = 0
SOFT_IRQ = 1

IRQ_TID = 0x10000000
IRQ_UNKOWN_TID = 0x20000000
INIT_STATUS_TID = 0x30000000
INIT_STATUS_TID_NAME = "InitStatus"
SELF_TID = 0x40000000
SELF_TID_NAME = "Self"
PID_NAME_SHIFT = 9
IRQ_HANDLE_TIME = 3000

EVENT_TYPE_RUNNING     = 0
EVENT_TYPE_PREEMPT     = 1
EVENT_TYPE_SLEEP       = 2
EVENT_TYPE_WAKED       = 3
EVENT_TYPE_WAKING      = 4

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

class task_event:
    def __init__(self, timestamp, pid):
        self.pid = pid
        self.timestamp = timestamp
        self.latency = 0
    def set_end_timestamp(self, timestamp):
        self.latency = timestamp - self.timestamp

class task_stat:
    def __init__(self, pid):
        self.pid = pid
        self.event = list()

class task_handle:
    def __init__(self, timestamp):
        self.running_status = dict()
        self.sleep_status = dict()
        self.timingline = list()
        self.timingline_stat = list()
        self.stat_stack = list()
        self.start_timestamp = timestamp
        event = task_event(timestamp, INIT_STATUS_TID)
        self.stat_stack.append(event)
    def waked_insert(self, timestamp, prev_pid):
        self.waked_list.append([timestamp, prev_pid])
        self.timingline.append([timestamp, EVENT_TYPE_WAKED, prev_pid])
    def waking_insert(self, timestamp, next_pid):
        self.waking_list.append([timestamp, next_pid])
        self.timingline.append([timestamp, EVENT_TYPE_WAKING, next_pid])
    def running_insert(self, timestamp):
        self.timingline.append([timestamp, EVENT_TYPE_RUNNING, timestamp])
        return
    def preempt_insert(self, timestamp):
        self.timingline.append([timestamp, EVENT_TYPE_PREEMPT, timestamp])
        return
    def sleep_insert(self, timestamp):
        self.timingline.append([timestamp, EVENT_TYPE_SLEEP, timestamp])
        return

def get_data_old(input_path="trace.dat.txt", output_path="trace.dat.any.txt"):
    data = read_input(input_path)
    irq_cpu=dict()
    task_dict = dict()
    pid_dict = dict()
    pid_dict[INIT_STATUS_TID] = INIT_STATUS_TID_NAME
    pid_dict[SELF_TID] = SELF_TID_NAME
    subword = data[1][PID_NAME_SHIFT:].split(':')[0].split()
    start_time=int(re.sub('[\.:]','',subword[-1]))
    for i in range(1, len(data)):
        sentence = data[i]  
        word = sentence[PID_NAME_SHIFT:].split(':')
        subword=word[0].split()
        comm = sentence[0:PID_NAME_SHIFT-1].split()[0]
        pid = int(subword[0].split('-')[-1])
        timestamp = int(re.sub('[\.:]','',subword[-1]))
        cpu = int(subword[-2][0])
        irq_context = subword[-2][3]
        if "sched_switch" in word[1]:
            subword = sentence.split("sched_switch:")[1].split('=')
            next_comm = subword[7].split(' next_pid')[0]
            pid_stat = subword[4]
            next_pid = int(subword[8].split(' next_prio')[0])
            # handle
            pid_dict[pid] = comm
            pid_dict[next_pid] = next_comm
            task_class = task_dict[pid]
            if task_class is None:
                task_class = task_handle(start_time)
                task_dict[pid] = task_class
            # 执行正常退出
            if "R" not in pid_stat:
                task_class.preempt_insert(timestamp)
            else:
                task_class.sleep_insert(timestamp)
            # 被强占，状态不变
            task_class = task_dict[next_pid]
            if task_class is None:
                task_class = task_handle(start_time)
                task_dict[next_pid] = task_class
            task_class.running_insert(timestamp)
        elif "sched_waking" in word[1]:
            subword = sentence.split("sched_waking:")[1].split('=')
            next_comm = subword[1].split(' pid')[0]
            next_pid = int(subword[2].split(' prio')[0])
            # handle
            if irq_context != '.':
                irq_list = irq_cpu[cpu]
                if irq_list is not None:
                    [irq_time, irq, irq_name, irq_type] = irq_list[-1]
                    if timestamp - irq_time < IRQ_HANDLE_TIME:
                        pid = IRQ_TID + irq
                        comm = irq_name + 'irq'
                    else:
                        pid = IRQ_UNKOWN_TID + pid
                        comm = next_comm + 'irq'
                else:
                    pid = IRQ_UNKOWN_TID + pid
                    comm = next_comm + 'unkown_irq'
            pid_dict[pid] = comm
            pid_dict[next_pid] = next_comm
            task_class = task_dict[pid]
            if task_class is None:
                task_class = task_handle(start_time)
                task_dict[pid] = task_class
            task_class.waking_insert(timestamp, next_pid)
            task_class = task_dict[next_pid]
            if task_class is None:
                task_class = task_handle(start_time)
                task_dict[next_pid] = task_class
            task_class.waked_insert(timestamp, pid)
        elif "softirq_entry" in word[1]:
            irq=int(word[4].split('=')[1])
            irq_name=word[5].split('=')[1]
            softirq_list = irq_cpu[cpu]
            if softirq_list is None:
                softirq_list = list()
                irq_cpu[cpu] = softirq_list
            softirq_list.append([timestamp, irq, irq_name, SOFT_IRQ])
        elif "irq_handler_entry" in word[1]:
            irq=int(word[4].split('=')[1])
            irq_name=word[5].split('=')[1]
            irq_list = irq_cpu[cpu]
            if irq_list is None:
                irq_list = list()
                irq_cpu[cpu] = irq_list
            irq_list.append([timestamp, irq, irq_name, HARD_IRQ])
    save_variable([irq_cpu, task_dict, pid_dict],output_path)

def get_data(input_path="trace.dat.txt", output_path="trace.dat.any.txt"):
    data = read_input(input_path)
    for i in range(1, len(data)):
        sentence = data[i]
        if "sched_switch" in sentence:
            stack_flag = 1
            continue
        if stack_flag == 1:
            if "=>" in sentence:
        if "sched_switch" in word[1]:
            subword = sentence.split("sched_switch:")[1].split('=')
            next_comm = subword[7].split(' next_pid')[0]
            pid_stat = subword[4]
            next_pid = int(subword[8].split(' next_prio')[0])
            # handle
            pid_dict[pid] = comm
            pid_dict[next_pid] = next_comm
            task_class = task_dict[pid]
            if task_class is None:
                task_class = task_handle(start_time)
                task_dict[pid] = task_class
            # 执行正常退出
            if "R" not in pid_stat:
                task_class.preempt_insert(timestamp)
            else:
                task_class.sleep_insert(timestamp)
            # 被强占，状态不变
            task_class = task_dict[next_pid]
            if task_class is None:
                task_class = task_handle(start_time)
                task_dict[next_pid] = task_class
            task_class.running_insert(timestamp)
        elif "sched_waking" in word[1]:
            subword = sentence.split("sched_waking:")[1].split('=')
            next_comm = subword[1].split(' pid')[0]
            next_pid = int(subword[2].split(' prio')[0])
            # handle
            if irq_context != '.':
                irq_list = irq_cpu[cpu]
                if irq_list is not None:
                    [irq_time, irq, irq_name, irq_type] = irq_list[-1]
                    if timestamp - irq_time < IRQ_HANDLE_TIME:
                        pid = IRQ_TID + irq
                        comm = irq_name + 'irq'
                    else:
                        pid = IRQ_UNKOWN_TID + pid
                        comm = next_comm + 'irq'
                else:
                    pid = IRQ_UNKOWN_TID + pid
                    comm = next_comm + 'unkown_irq'
            pid_dict[pid] = comm
            pid_dict[next_pid] = next_comm
            task_class = task_dict[pid]
            if task_class is None:
                task_class = task_handle(start_time)
                task_dict[pid] = task_class
            task_class.waking_insert(timestamp, next_pid)
            task_class = task_dict[next_pid]
            if task_class is None:
                task_class = task_handle(start_time)
                task_dict[next_pid] = task_class
            task_class.waked_insert(timestamp, pid)
        elif "softirq_entry" in word[1]:
            irq=int(word[4].split('=')[1])
            irq_name=word[5].split('=')[1]
            softirq_list = irq_cpu[cpu]
            if softirq_list is None:
                softirq_list = list()
                irq_cpu[cpu] = softirq_list
            softirq_list.append([timestamp, irq, irq_name, SOFT_IRQ])
        elif "irq_handler_entry" in word[1]:
            irq=int(word[4].split('=')[1])
            irq_name=word[5].split('=')[1]
            irq_list = irq_cpu[cpu]
            if irq_list is None:
                irq_list = list()
                irq_cpu[cpu] = irq_list
            irq_list.append([timestamp, irq, irq_name, HARD_IRQ])
    save_variable([irq_cpu, task_dict, pid_dict],output_path)

if __name__ == '__main__':
    get_data(INPUT_FILE_WITH_STACK, OUTPUT_FILE)