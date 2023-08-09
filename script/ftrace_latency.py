#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 16 00:19:13 2018

@author: Hao Lan
"""
import re
import pickle
import json

INPUT_FTRACE_FILE="langraph/ftrace.log"
INPUT_FTRACE_SYMBOL_FILE="langraph/ftrace_symbol.log"
INPUT_FTRACE_FORMAT_FILE="langraph/ftrace_format.log"
INPUT_PERF_JSON="langraph/perf.data.json"
INPUT_PERF_SCRIPT="langraph/perf.log"

OUTPUT_FILE="langraph.out.json"
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

TRACE_RETURN_TRUE=0
TRACE_RETURN_FALSE=1
TRACE_RETURN_STACK=2
TRACE_RETURN_COMMENT=3
TRACE_STACK_NOT=0
TRACE_STACK_UNDEF=1
TRACE_STACK_KERNEL=2
TRACE_STACK_USER=3

TRACE_FORMAT_TYPE_FTRACE=0
TRACE_FORMAT_TYPE_PERF_JSON=1
TRACE_FORMAT_TYPE_PERF_SCRIPT=2

PERF_NAME_INDEX=0
PERF_TID_INDEX=2
PERF_PID_INDEX=1
PERF_CPU_INDEX=3
PERF_TIMESTAMP_INDEX=4
PERF_EVENT_INDEX=5
PERF_SUBEVENT_INDEX=6
DELAY_TOTAL = 0
DELAY_CPU = 1
DELAY_TID = 2
DELAY_IRQ = 3
DELAY_SOFTIRQ = 4
DELAY_MAX = 5

cpu_list={}
tid_list={}
pid_tid_list={}
irq_list={}
vec_list={}
trace_list=[]
pid_list={}
te_list=[]
stack_hash_list = {}
user_symbol_list = {}
timestamp_start=-1.0
timestamp_end=-1.0
irq_tid=int(0)
vec_tid=int(0)
cpu_tid=int(0)

pid_valid=re.compile("\d+")

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
            print(line)
            data = list()
        data.append(line)
    return data

event_match={
    "sched_kthread_stop" : re.compile("comm=(\S+) pid=(\d+)"),
    "sched_kthread_stop_ret" : re.compile("ret=(\d+)"),
    "sched_kthread_work_execute_end" : re.compile("work struct ([-+]?(0[xX])?[\dA-Fa-f]+): function (\S+)"),
    "sched_kthread_work_execute_start" : re.compile("work struct ([-+]?(0[xX])?[\dA-Fa-f]+): function (\S+)"),
    "sched_kthread_work_queue_work" : re.compile("work struct=([-+]?(0[xX])?[\dA-Fa-f]+) function=(\S+) worker=([-+]?(0[xX])?[\dA-Fa-f]+)"),
    "sched_migrate_task" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+) orig_cpu=(\d+) dest_cpu=(\d+)"),
    "sched_move_numa" : re.compile("pid=(\d+) tgid=(\d+) ngid=(\d+) src_cpu=(\d+) src_nid=(\d+) dst_cpu=(\d+) dst_nid=(\d+)"),
    "sched_pi_setprio" : re.compile("comm=(\S+) pid=(\d+) oldprio=(\d+) newprio=(\d+)"),
    "sched_process_exec" : re.compile("filename=(\S+) pid=(\d+) old_pid=(\d+)"),
    "sched_process_exit" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+)"),
    "sched_process_fork" : re.compile("comm=(\S+) pid=(\d+) child_comm=(\S+) child_pid=(\d+)"),
    "sched_process_free" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+)"),
    "sched_process_hang" : re.compile("comm=(\S+) pid=(\d+)"),
    "sched_process_wait" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+)"),
    "sched_stat_blocked" : re.compile("comm=(\S+) pid=(\d+) delay=(\d+) \[ns\]"),
    "sched_stat_iowait" : re.compile("comm=(\S+) pid=(\d+) delay=(\d+) \[ns\]"),
    "sched_stat_runtime" : re.compile("comm=(\S+) pid=(\d+) runtime=(\d+) \[ns\] vruntime=(\d+) \[ns\]"),
    "sched_stat_sleep" : re.compile("comm=(\S+) pid=(\d+) delay=(\d+) \[ns\]"),
    "sched_stat_wait" : re.compile("comm=(\S+) pid=(\d+) delay=(\d+) \[ns\]"),
    "sched_stick_numa" : re.compile("src_pid=(\d+) src_tgid=(\d+) src_ngid=(\d+) src_cpu=(\d+) src_nid=(\d+) dst_pid=(\d+) dst_tgid=(\d+) dst_ngid=(\d+) dst_cpu=(\d+) dst_nid=(\d+)"),
    "sched_swap_numa" : re.compile("src_pid=(\d+) src_tgid=(\d+) src_ngid=(\d+) src_cpu=(\d+) src_nid=(\d+) dst_pid=(\d+) dst_tgid=(\d+) dst_ngid=(\d+) dst_cpu=(\d+) dst_nid=(\d+)"),
    "sched_switch" : re.compile("prev_comm=(\S+) prev_pid=(\d+) prev_prio=(\d+) prev_state=(\S+) ==> next_comm=(\S+) next_pid=(\d+) next_prio=(\d+)"),
    "sched_wait_task" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+)"),
    "sched_wake_idle_without_ipi" : re.compile("cpu=(\d+)"),
    "sched_wakeup" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+) target_cpu=(\d+)"),
    "sched_wakeup_new" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+) target_cpu=(\d+)"),
    "sched_waking" : re.compile("comm=(\S+) pid=(\d+) prio=(\d+) target_cpu=(\d+)"),
    "irq_handler_entry" : re.compile("irq=(\d+) name=(\S+)"),
    "irq_handler_exit" : re.compile("irq=(\d+) ret=(\S+)"),
    "softirq_entry" : re.compile("vec=(\d+) \[action=(\S+)\]"),
    "softirq_exit" : re.compile("vec=(\d+) \[action=(\S+)\]"),
    "softirq_raise" : re.compile("vec=(\d+) \[action=(\S+)\]"),
    "perf" : re.compile("(\S+ *\S+) * (-*\d+)\/(-*\d+) *\[(\d+)\] *(\d+\.\d+): *(\S+):(\S+):*"),
}

def stack_handle(line, priv):
    key_word = line.split()
    [stack_name_list, stack_addr_list] = priv
    key_word_len = len(key_word)
    if key_word_len == 3:
        stack_name_list.append(key_word[1])
        stack_addr_list.append(key_word[2])
    elif key_word_len == 4:
        stack_name_list.append(key_word[1])
        stack_addr_list.append(key_word[3])
    elif key_word_len == 2:
        stack_name_list.append(key_word[1])
        stack_addr_list.append(key_word[1])
    else:
        print("Error stack "+line)

def cpu_clock_handle(line, priv):
    [[stack_name_list, stack_addr_list], [ustack_name_list, ustack_addr_list]] = priv
    key_word = line.split()
    key_word_len = len(key_word)
    if key_word_len > 1:
        if int(key_word[0],16) > 0xf000000000000000:
            stack_name_list.append(key_word[1])
            stack_addr_list.append(key_word[0])
        else:
            ustack_name_list.append(key_word[1])
            ustack_addr_list.append(key_word[0])
    elif key_word_len == 1:
        if int(key_word[0],16) > 0xf000000000000000:
            stack_name_list.append(key_word[0])
            stack_addr_list.append(key_word[0])
        else:
            ustack_name_list.append(key_word[0])
            ustack_addr_list.append(key_word[0])
    else:
        print("Error stack "+line)

def null_init(ev):
    return

def cpu_clock_init(ev):
    ev.priv = [ev.kernel_stack, ev.user_stack]
    return

def stack_init(ev):
    ev.priv = [[],[]]
    if ev.event_name == "<stack trace>":
        ev.is_stack = TRACE_STACK_KERNEL
    else:
        ev.is_stack = TRACE_STACK_USER
    return

def irq_init(ev):
    irq_info = ev.priv
    irq_num = irq_info[0]
    if irq_num not in irq_list:
        irq_ev_list = []
        irq_list[irq_num] = irq_ev_list
    else:
        irq_ev_list = irq_list[irq_num]
    irq_ev_list.append(ev)
    return

def softirq_init(ev):
    vec_info = ev.priv
    vec_num = vec_info[0]
    if vec_num not in vec_list:
        vec_ev_list = []
        vec_list[vec_num] = vec_ev_list
    else:
        vec_ev_list = vec_list[vec_num]
    vec_ev_list.append(ev)
    return

def null_handle(line, priv):
    return

mod_type = {
    "sched" : ["sched_kthread_stop",
        "sched_kthread_stop_ret",
        "sched_kthread_work_execute_end",
        "sched_kthread_work_execute_start",
        "sched_kthread_work_queue_work",
        "sched_migrate_task",
        "sched_move_numa",
        "sched_pi_setprio",
        "sched_process_exec",
        "sched_process_exit",
        "sched_process_fork",
        "sched_process_free",
        "sched_process_hang",
        "sched_process_wait",
        "sched_stat_blocked",
        "sched_stat_iowait",
        "sched_stat_runtime",
        "sched_stat_sleep",
        "sched_stat_wait",
        "sched_stick_numa",
        "sched_swap_numa",
        "sched_switch",
        "sched_wait_task",
        "sched_wake_idle_without_ipi",
        "sched_wakeup",
        "sched_wakeup_new",
        "sched_waking"],
    "irq" : ["irq_handler_entry",
        "irq_handler_exit",
        "softirq_entry",
        "softirq_exit",
        "softirq_raise"],
    "ftrace" : ["ftrace",
        "<stack trace>",
        "<user stack trace>"],
    "perf" : ["perf",
        "cpu-clock",
        "cpu-cycles"]
}

event_type = {
    "sched_kthread_stop"               : ["sched",  null_init, null_handle, []],
    "sched_kthread_stop_ret"           : ["sched",  null_init, null_handle, []],
    "sched_kthread_work_execute_end"   : ["sched",  null_init, null_handle, []],
    "sched_kthread_work_execute_start" : ["sched",  null_init, null_handle, []],
    "sched_kthread_work_queue_work"    : ["sched",  null_init, null_handle, []],
    "sched_migrate_task"               : ["sched",  null_init, null_handle, []],
    "sched_move_numa"                  : ["sched",  null_init, null_handle, []],
    "sched_pi_setprio"                 : ["sched",  null_init, null_handle, []],
    "sched_process_exec"               : ["sched",  null_init, null_handle, []],
    "sched_process_exit"               : ["sched",  null_init, null_handle, []],
    "sched_process_fork"               : ["sched",  null_init, null_handle, []],
    "sched_process_free"               : ["sched",  null_init, null_handle, []],
    "sched_process_hang"               : ["sched",  null_init, null_handle, []],
    "sched_process_wait"               : ["sched",  null_init, null_handle, []],
    "sched_stat_blocked"               : ["sched",  null_init, null_handle, []],
    "sched_stat_iowait"                : ["sched",  null_init, null_handle, []],
    "sched_stat_runtime"               : ["sched",  null_init, null_handle, []],
    "sched_stat_sleep"                 : ["sched",  null_init, null_handle, []],
    "sched_stat_wait"                  : ["sched",  null_init, null_handle, []],
    "sched_stick_numa"                 : ["sched",  null_init, null_handle, []],
    "sched_swap_numa"                  : ["sched",  null_init, null_handle, []],
    "sched_switch"                     : ["sched",  null_init, null_handle, []],
    "sched_wait_task"                  : ["sched",  null_init, null_handle, []],
    "sched_wake_idle_without_ipi"      : ["sched",  null_init, null_handle, []],
    "sched_wakeup"                     : ["sched",  null_init, null_handle, []],
    "sched_wakeup_new"                 : ["sched",  null_init, null_handle, []],
    "sched_waking"                     : ["sched",  null_init, null_handle, []],
    "irq_handler_entry"                : ["irq",    irq_init, null_handle, []],
    "irq_handler_exit"                 : ["irq",    irq_init, null_handle, []],
    "softirq_entry"                    : ["irq",    softirq_init, null_handle, []],
    "softirq_exit"                     : ["irq",    softirq_init, null_handle, []],
    "softirq_raise"                    : ["irq",    softirq_init, null_handle, []],
    "<stack trace>"                    : ["ftrace", stack_init, stack_handle, []],
    "<user stack trace>"               : ["ftrace", stack_init, stack_handle, []],
    "cpu-clock"                        : ["perf", cpu_clock_init, cpu_clock_handle, []],
    "cpu-cycles"                        : ["perf", cpu_clock_init, cpu_clock_handle, []],
}

def event_type_init():
    for mod_name, init_op, handle_op, event_type_list in event_type.values():
        event_type_list.clear()

"<...>-154717  ( 154717) [000] d.... 27117.357065: sched_stat_runtime: "
class trace_event:
    def init_stack(self):
        if self.cpu not in cpu_list:
            return
        else:
            cpu_ev_list = cpu_list[self.cpu]
        if len(cpu_ev_list) == 0:
            return
        cpu_ev = cpu_ev_list[-1]
        if self.is_stack == TRACE_STACK_KERNEL:
            cpu_ev.kernel_stack = self.priv[:]
        else:
            cpu_ev.user_stack = self.priv[:]
        return

    def init_normal(self):
        if self.cpu not in cpu_list:
            cpu_ev_list = []
            cpu_list[self.cpu] = cpu_ev_list
        else:
            cpu_ev_list = cpu_list[self.cpu]
        cpu_ev_list.append(self)
        if self.tid not in tid_list:
            tid_ev_list = []
            tid_list[self.tid] = tid_ev_list
        else:
            tid_ev_list = tid_list[self.tid]
        tid_ev_list.append(self)
        if self.pid not in pid_tid_list:
            pid_ev_list = dict()
            pid_tid_list[self.pid] = pid_ev_list
            pid_ev_list["name"] = ""
        else:
            pid_ev_list = pid_tid_list[self.pid]
        if self.pid == self.tid:
            pid_ev_list["name"] = self.name
        if self.tid not in pid_ev_list:
            pid_ev_list[self.tid] = self.name
        trace_list.append(self)
        return
    def init_common(self):
        if self.is_stack != TRACE_STACK_NOT:
            self.init_stack()
        else:
            self.init_normal()

    def handle_pid_tid(self):
        if pid_valid.match(self.pid) is not None:
            self.pid = int(self.pid)
        else:
            self.pid = int(0)
        if pid_valid.match(self.tid) is not None:
            self.tid = int(self.tid)
        else:
            self.tid = int(0)

    def ftrace_event(self, line=""):
        self.raw = line
        self.available = TRACE_RETURN_TRUE
        if line[0:4] == ' => ':
            self.available = TRACE_RETURN_STACK
            return
        elif line.__len__() == 0:
            self.available = TRACE_RETURN_FALSE
            return
        elif line[0] == '#':
            self.available = TRACE_RETURN_COMMENT
            return
        self.is_stack = TRACE_STACK_NOT
        self.kernel_stack = [[], []]
        self.user_stack = [[], []]
        self.kernel_stack_hash = int(0)
        self.user_stack_hash = int(0)
        self.stack_hash = int(0)
        self.cpu_delay = int(-1)
        self.tid_delay = int(-1)
        self.cpu_index = int(-1)
        self.tid_index = int(-1)
        self.name  = line[ NAME_START: NAME_END].strip()
        self.tid   = line[  TID_START:  TID_END].strip()
        self.pid   = line[  PID_START:  PID_END].strip()
        self.handle_pid_tid()
        self.cpu   = int(line[  CPU_START:  CPU_END].strip())
        self.state = line[STATE_START:STATE_END].strip()
        key_word = line[TID_START:-1].split(':')
        self.timestamp = float(key_word[0].split()[-1])
        self.event_name = key_word[1].strip()
        if self.event_name in event_type:
            [mod_name, init_op, handle_op, event_type_list] = event_type[self.event_name]
            (start, end) = re.search(self.event_name, line).span()
            event_type_list.append(self)
            info = line[end + 2 : -1]
            if self.event_name not in event_match:
                self.priv = info
                init_op(self)
                self.init_common()
                return
            pattern = event_match[self.event_name]
            match = pattern.match(info)
            if match is not None:
                self.priv = match.groups()
                init_op(self)
            else:
                self.priv = info
                init_op(self)
        else:
            self.priv = line
        self.init_common()

    def perf_json_stack(self, te_json={}):
        [stack_name_list, stack_addr_list] = self.kernel_stack
        [ustack_name_list, ustack_addr_list] = self.user_stack
        for callchain in te_json['callchain']:
            if int(callchain['ip'],16) > 0xf000000000000000:
                if 'ip' in callchain:
                    stack_name_list.append(callchain['ip'])
                if 'symbol' in callchain:
                    stack_addr_list.append(callchain['symbol'])
            else:
                if 'ip' in callchain:
                    ustack_name_list.append(callchain['ip'])
                if 'symbol' in callchain:
                    ustack_addr_list.append(callchain['symbol'])

    def perf_json_event(self, te_json={}):
        self.raw = te_json
        self.available = TRACE_RETURN_TRUE
        self.is_stack = TRACE_STACK_NOT
        self.kernel_stack = [[], []]
        self.user_stack = [[], []]
        self.kernel_stack_hash = int(0)
        self.user_stack_hash = int(0)
        self.stack_hash = int(0)
        self.delay = [int(0)] * DELAY_MAX
        self.index = [int(0)] * DELAY_MAX
        self.tid_index = int(-1)
        self.name  = te_json['comm']
        self.tid   = te_json['tid']
        self.pid   = te_json['pid']
        self.cpu   = int(te_json['cpu'])
        self.state = ""
        self.timestamp = float(te_json['timestamp']) / 1000000
        self.event_name = "cpu-clock"
        self.perf_json_stack(te_json)

    def perf_script_event(self, line=""):
        self.raw = line
        self.available = TRACE_RETURN_TRUE
        if line[0] == '\t' and len(line.split()) >= 1:
            self.available = TRACE_RETURN_STACK
            return
        elif line.__len__() == 0:
            self.available = TRACE_RETURN_COMMENT
            return
        elif line[0] == '#':
            self.available = TRACE_RETURN_COMMENT
            return
        elif line[0] == '\n':
            self.available = TRACE_RETURN_COMMENT
            return
        pattern = event_match['perf']
        match = pattern.match(line)
        if match is None:
            self.available = TRACE_RETURN_FALSE
            return
        perf_hand = match.groups()
        #print(perf_hand)
        self.is_stack = TRACE_STACK_NOT
        self.kernel_stack = [[], []]
        self.user_stack = [[], []]
        self.kernel_stack_hash = int(0)
        self.user_stack_hash = int(0)
        self.stack_hash = int(0)
        self.cpu_delay = int(-1)
        self.tid_delay = int(-1)
        self.cpu_index = int(-1)
        self.tid_index = int(-1)
        self.name  = perf_hand[PERF_NAME_INDEX]
        self.tid   = perf_hand[PERF_TID_INDEX]
        self.pid   = perf_hand[PERF_PID_INDEX]
        self.handle_pid_tid()
        self.cpu   = int(perf_hand[PERF_CPU_INDEX])
        self.state = ""
        self.timestamp = float(perf_hand[PERF_TIMESTAMP_INDEX])
        if perf_hand[PERF_EVENT_INDEX] == "cpu-clock" or perf_hand[PERF_EVENT_INDEX] == "cpu-cycles":
            self.event_name = perf_hand[PERF_EVENT_INDEX]
        else:
            self.event_name = perf_hand[PERF_SUBEVENT_INDEX].strip(':')
        if self.event_name in event_type:
            [mod_name, init_op, handle_op, event_type_list] = event_type[self.event_name]
            (start, end) = match.span()
            event_type_list.append(self)
            info = line[end : -1].strip()
            if self.event_name not in event_match:
                self.priv = info
                init_op(self)
                self.init_common()
                return
            pattern = event_match[self.event_name]
            match = pattern.match(info)
            if match is not None:
                self.priv = match.groups()
                init_op(self)
            else:
                self.priv = info
                init_op(self)
        else:
            self.priv = line
        self.init_common()

    def __init__(self, line, format_type):
        #print(line, format_type)
        self.format_type = format_type
        if format_type == TRACE_FORMAT_TYPE_FTRACE:
            self.ftrace_event(line)
        elif format_type == TRACE_FORMAT_TYPE_PERF_SCRIPT:
            self.perf_script_event(line)
        elif format_type == TRACE_FORMAT_TYPE_PERF_JSON:
            self.perf_json_event(line)

    def get_available(self):
        return self.available
    def handle(self, line):
        if self.available != TRACE_RETURN_TRUE:
            return
        if self.event_name in event_type:
            [mod_name, init_op, handle_op, event_type_list] = event_type[self.event_name]
            handle_op(line, self.priv)

def get_irq_name(event_name, irq_ev):
    (irq_num, irq_name) = irq_ev[0].priv
    for ev in irq_ev:
        if event_name == ev.event_name:
            (irq_num, irq_name) = ev.priv
            return irq_name
    return irq_name

def irq_to_thread_name(irq_list_name, event_name, pid_cur, irq_ev_list):
    global pid_tid_list
    irq_pid_list = {'name' : irq_list_name}
    irq_pid_max = pid_cur
    for irq_id in irq_ev_list.keys():
        irq_pid = pid_cur + int(irq_id)
        irq_pid_max = max(irq_pid_max, irq_pid)
        irq_name = get_irq_name(event_name, irq_ev_list[irq_id])
        irq_pid_list[irq_pid] = irq_name
    pid_tid_list[pid_cur] = irq_pid_list
    return irq_pid_max

def cpu_to_thread_name(cpu_list_name, pid_cur, cpu_ev_list):
    global pid_tid_list
    cpu_pid_list = {'name' : cpu_list_name}
    cpu_pid_max = pid_cur
    for cpu_id in cpu_ev_list.keys():
        cpu_pid = pid_cur + int(cpu_id)
        cpu_pid_max = max(cpu_pid_max, cpu_pid)
        cpu_name = cpu_list_name+'_'+str(cpu_id)
        cpu_pid_list[cpu_pid] = cpu_name
    pid_tid_list[pid_cur] = cpu_pid_list
    return cpu_pid_max

def get_max_tid():
    pid_name_list=list()
    for pid in pid_tid_list:
        tid_id_list = pid_tid_list[pid]
        for tid in tid_id_list:
            if tid == "name":
                continue
            pid_name_list.append(tid)
    return max(pid_name_list)

def init_metadata_event():
    global cpu_tid
    global irq_tid
    global vec_tid
    pid_cur = get_max_tid() + 1
    cpu_tid = pid_cur
    pid_cur = cpu_to_thread_name("langrah_cpu", pid_cur, cpu_list) + 1
    irq_tid = pid_cur
    pid_cur = irq_to_thread_name("langrah_irq", 'irq_handler_entry', pid_cur, irq_list) + 1
    vec_tid = pid_cur
    pid_cur = irq_to_thread_name("langrah_softirq", 'softirq_entry', pid_cur, vec_list)

def init_trace_stack():
    for te in trace_list:
        te.kernel_stack_hash = hash(str(te.kernel_stack[0]))
        te.user_stack_hash = hash(str(te.user_stack[0]))
        te.stack_hash = hash(str([te.kernel_stack[0],te.user_stack[0]]))

def init_pid_event():
    for pid in pid_tid_list:
        tid_id_list = pid_tid_list[pid]
        pid_event_list = []
        for tid in tid_id_list:
            if tid == "name":
                continue
            pid_event_list.extend(tid_list[tid])
        pid_event_list.sort(key=lambda x: x.timestamp)
        pid_list[pid] = pid_event_list

def init_stack_hash():
    for te in trace_list:
        hash_id = te.stack_hash
        if hash_id in stack_hash_list:
            hash_num = stack_hash_list[hash_id]
            stack_hash_list[hash_id] = hash_num + 1
        else:
            stack_hash_list[hash_id] = 1

USER_SYMBOL_EXEC_FILE_INDEX=2
USER_SYMBOL_ADDR_INDEX=3
USER_SYMBOL_FUNC_NAME_INDEX=5
USER_SYMBOL_FILE_LINE_INDEX=7
USER_SYMBOL_SIZE=8
def parse_user_symbol(line):
    word = line.split()
    if len(word) != USER_SYMBOL_SIZE:
        return
    exec_file = word[USER_SYMBOL_EXEC_FILE_INDEX]
    function_addr = word[USER_SYMBOL_ADDR_INDEX]
    function_name = word[USER_SYMBOL_FUNC_NAME_INDEX]
    if "??" in function_name:
        function_name = "user_symbol_" + exec_file.split('/')[-1]
    user_symbol_index="%s[+%s]" %(exec_file, function_addr)
    user_symbol_list[user_symbol_index] = [function_name, function_addr]

def parse_delay_list(delay_list, delay_offset):
    for ev in delay_list.values():
        index = int(0)
        timestamp = timestamp_start
        for te in ev:
            te.index[delay_offset] = index
            te.delay[delay_offset] = te.timestamp - timestamp
            index = index + 1
            timestamp = te.timestamp

def parse_delay():
    parse_delay_list(tid_list, DELAY_TID)
    parse_delay_list(cpu_list, DELAY_CPU)
    parse_delay_list(vec_list, DELAY_SOFTIRQ)
    parse_delay_list(irq_list, DELAY_IRQ)

def init_list(ls):
    if type(ls) != dict:
        return
    for evlist in ls.values():
        if type(evlist) == list:
            evlist.sort(key=lambda x: x.timestamp)

def init_global():
    global timestamp_start
    global timestamp_end
    trace_list.sort(key=lambda x: x.timestamp)
    init_list(cpu_list)
    init_list(irq_list)
    init_list(tid_list)
    init_list(vec_list)
    init_trace_stack()
    init_stack_hash()
    timestamp_start = trace_list[0].timestamp
    timestamp_end = trace_list[-1].timestamp
    parse_delay()
    init_metadata_event()

def parse_data(data, format_type=TRACE_FORMAT_TYPE_FTRACE):
    data_len = len(data)
    event_type_init()
    if data_len == 0:
        return
    last_te = trace_event(data[0], format_type)
    for i in range(1, data_len):
        line = data[i]
        #print(line)
        te = trace_event(line, format_type)
        if te.get_available() == TRACE_RETURN_FALSE:
            print(data[i],"TRACE_RETURN_FALSE")
            continue
        if te.get_available() == TRACE_RETURN_COMMENT:
            if "# user_symbol:" in line:
                parse_user_symbol(line)
            continue
        if te.get_available() == TRACE_RETURN_STACK:
            if last_te.get_available() == TRACE_RETURN_TRUE:
                last_te.handle(line)
                continue
            else:
                print(data[i],"TRACE_RETURN_FALSE")
                continue
        last_te = te
        te_list.append(te)
    return te_list

def parse_perf_json(input_filename=INPUT_PERF_JSON):
    fd=open(input_filename)
    json_data=json.load(fd)
    for json_te in json_data['samples']:
        te = trace_event(json_te, TRACE_FORMAT_TYPE_PERF_JSON)
        if te.get_available() == TRACE_RETURN_FALSE:
            print("TRACE_RETURN_FALSE")
            continue
        te_list.append(te)
    fd.close()
    del json_data
    return te_list

def reset_resource():
    global cpu_list
    global tid_list
    global pid_tid_list
    global irq_list
    global vec_list
    global trace_list
    global pid_list
    global te_list
    global stack_hash_list
    global user_symbol_list
    global timestamp_start
    global timestamp_end
    cpu_list={}
    tid_list={}
    pid_tid_list={}
    irq_list={}
    vec_list={}
    trace_list=[]
    pid_list={}
    te_list=[]
    stack_hash_list = {}
    user_symbol_list = {}
    timestamp_start=-1.0
    timestamp_end=-1.0

def event_type_priv_max(event="<user stack trace>"):
    if event not in event_type:
        print("Event %s not in event_type." %event)
        return
    [name, init_op, handle_op, ev_list] = event_type[event]
    max_size = 0
    for ev in ev_list:
        if max_size < len(ev.priv):
            max_size = len(ev.priv)
    print("%s max_size is %d." %(event, max_size))

def event_type_print_priv():
    for name in event_type:
        [mod_name, init, handle, ev] = event_type[name]
        if len(ev) != 0:
            print(name, ev[0].priv)
        else:
            print(name)

def event_check_stack(data, te_list):
    te_len =len(te_list)
    for i in range(te_len):
        if te_list[i].event_name == "<stack trace>" and te_list[i].event_name != "<user stack trace>":
            print(te_list[i].timestamp)

def event_stack_stat(te_list):
    te_len =len(te_list)
    stack_stat_list = {}
    for i in range(te_len):
        te = te_list[i]
        stat = te.state
        if stat[2] != '.':
            continue
        hash_id = te.kernel_stack_hash
        if hash_id in stack_stat_list:
            [stack, stack_num] = stack_stat_list[hash_id]
            stack_stat_list[hash_id] = [stack, stack_num + 1]
        else:
            stack_stat_list[hash_id] = [te.kernel_stack.priv, 1]
    for s in stack_stat_list:
        print(stack_stat_list[s][1], stack_stat_list[s][0][0])
    return stack_stat_list

def print_all_te(trace_list):
    for te in trace_list:
        print('%d\t%08X %s %s|%s' %(stack_hash_list[te.stack_hash], abs(te.stack_hash), te.raw.strip(), te.kernel_stack.priv[0], te.user_stack.priv[0]))

def print_all_te_irq(trace_list):
    for te in trace_list:
        if len(te.kernel_stack[0]) > 0:
            te.kernel_stack[0].reverse()
        if len(te.user_stack[0]) > 0:
            te.user_stack[0].reverse()
        print('%s\t%s\t%s\t%d, %s, %s' %(te.state, te.event_name, te.tid, te.cpu, te.kernel_stack[0], te.user_stack[0]))
        if len(te.kernel_stack[0]) > 0:
            te.kernel_stack[0].reverse()
        if len(te.user_stack[0]) > 0:
            te.user_stack[0].reverse()

def print_all_cpu_te(cpu_list):
    for i in range(4):
        trace_list = cpu_list[i]
        for te in trace_list:
            print(te.raw.strip())

"""
perf-exec   27804/27804   [000]   959.661520: cpu-clock:ppp:                         
	ffffffffa85ba87a unmap_page_range+0x38a ([kernel.kallsyms])
	ffffffffa85baa9e unmap_single_vma+0x7e ([kernel.kallsyms])
	ffffffffa85badf5 unmap_vmas+0xe5 ([kernel.kallsyms])
	ffffffffa85cab5a exit_mmap+0xda ([kernel.kallsyms])
	ffffffffa82e4218 __mmput+0x48 ([kernel.kallsyms])
	ffffffffa82e4351 mmput+0x31 ([kernel.kallsyms])
	ffffffffa8683d56 exec_mmap+0x176 ([kernel.kallsyms])
	ffffffffa8686e2b begin_new_exec+0x11b ([kernel.kallsyms])
	ffffffffa870fa38 load_elf_binary+0x2d8 ([kernel.kallsyms])
	ffffffffa8683fea search_binary_handler+0xda ([kernel.kallsyms])
	ffffffffa86844c6 exec_binprm+0x56 ([kernel.kallsyms])
	ffffffffa868634c bprm_execve.part.0+0x18c ([kernel.kallsyms])
	ffffffffa868645e bprm_execve+0x5e ([kernel.kallsyms])
	ffffffffa8686648 do_execveat_common.isra.0+0x198 ([kernel.kallsyms])
	ffffffffa86869a7 __x64_sys_execve+0x37 ([kernel.kallsyms])
	ffffffffa928c1ac do_syscall_64+0x5c ([kernel.kallsyms])
	ffffffffa94000aa entry_SYSCALL_64_after_hwframe+0x72 ([kernel.kallsyms])

swapper       0/0       [001]   959.661867: cpu-clock:ppp:                         
"""
def event_to_perf(te):
    if te.pid == "-------":
        print('%s\t0\t[00%d]\t%0.06f:\t1000\t%s:' %(te.name, te.cpu, te.timestamp, te.event_name))
    else:
        print('%s\t%s\t[00%d]\t%0.06f:\t1000\t%s:' %(te.name, te.pid, te.cpu, te.timestamp, te.event_name))
    if len(te.kernel_stack[0]) > 0:
        for i in range(len(te.kernel_stack[0])):
            stack=te.kernel_stack[0][i]
            addr=te.kernel_stack[1][i]
            print("\t%s %s ([kernel.kallsyms])" %(addr.strip('<').strip('>'), stack))
    if len(te.user_stack[0]) > 0:
        for i in range(len(te.user_stack[0])):
            stack=te.user_stack[0][i]
            addr=te.user_stack[1][i]
            print("\t%s %s (%s)" %(addr.strip('<').strip('>'), stack, te.name))
    print("")

def conver_to_perf():
    for te in trace_list:
        event_to_perf(te)

class trace_event_json_item:
    def __init__(self):
        self.name = str('')
        self.args = {}
        self.cat = str('')
        self.pid = int(0)
        self.tid = int(0)
        self.ts = int(0)
        self.dur = int(0)
        self.ph = str('')
        self.bind_id = str('')
        self.flow_in = bool(0)
        self.flow_out = bool(0)

class trace_event_json:
    def get_json_tree(self):
        return self.json_tree

    def clean_json_tree(self):
        self.json_tree={}
        self.json_tree['traceEvents'] = list()
        self.json_tree_result=[self.json_tree]

    def save_json(self, output=OUTPUT_FILE):
        fd = open(output, 'w+')
        fd.write(json.dumps(self.json_tree_result, indent=0))

    def __init__(self):
        self.clean_json_tree()

    def format_item(self, item):
        json_item = dict()
        json_item['name'] = item.name
        json_item['args'] = item.args
        json_item['cat'] = item.cat
        json_item['pid'] = item.pid
        json_item['tid'] = item.tid
        json_item['ts'] = item.ts
        json_item['dur'] = item.dur
        json_item['ts'] = item.ts
        json_item['ph'] = item.ph
        if item.bind_id != '':
            json_item['bind_id'] = item.bind_id
            json_item['flow_in'] = item.flow_in
            json_item['flow_out'] = item.flow_out
        self.json_tree['traceEvents'].append(json_item)

    def format_pidname_item(self, name, pid, tid):
        item = trace_event_json()
        item.name = "process_name"
        item.args['name'] = name
        item.pid = pid
        item.tid = tid
        item.ts = int(0)
        item.cat = '__metadata'
        item.ph = "M"
        self.format_item(item)

    def format_tidname_item(self, name, pid, tid):
        item = trace_event_json()
        item.name = "thread_name"
        item.args['name'] = name
        item.pid = pid
        item.tid = tid
        item.ts = int(0)
        item.cat = '__metadata'
        item.ph = "M"
        self.format_item(item)

    def json_metadata_thread_name(self, pid_tid_list):
        for pid in pid_tid_list:
            tid_id_list = pid_tid_list[pid]
            for tid in tid_id_list:
                pid_name = tid_id_list[tid]
                if tid != "name":
                    self.format_tidname_item(pid_name, pid, tid)
                else:
                    self.format_pidname_item(pid_name, pid, pid)

if __name__ == '__main__':
    data = read_input(INPUT_FTRACE_FILE)
    te_list=parse_data(data, format_type=TRACE_FORMAT_TYPE_FTRACE)
    data = read_input(INPUT_PERF_SCRIPT)
    te_list=parse_data(data, format_type=TRACE_FORMAT_TYPE_PERF_SCRIPT)
    init_global()
    #event_stack_stat(trace_list)
    #print_all_te(trace_list)
    #print_all_te_irq(trace_list)
    #print_all_cpu_te(cpu_list)
