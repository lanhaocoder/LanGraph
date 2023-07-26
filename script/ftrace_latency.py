#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 16 00:19:13 2018

@author: Hao Lan
"""
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

TRACE_RETURN_TRUE=0
TRACE_RETURN_FALSE=1
TRACE_RETURN_STACK=2
TRACE_RETURN_COMMENT=3
TRACE_STACK_NOT=0
TRACE_STACK_UNDEF=1
TRACE_STACK_KERNEL=2
TRACE_STACK_USER=3

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
    "softirq_raise" : re.compile("vec=(\d+) \[action=(\S+)\]")
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

def null_init(ev):
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
    "ftrace" : ["<stack trace>",
        "<user stack trace>"]
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
    "<user stack trace>"               : ["ftrace", stack_init, stack_handle, []]
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
            cpu_ev.kernel_stack = self
        else:
            cpu_ev.user_stack = self
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
            pid_ev_list = set()
            pid_tid_list[self.pid] = pid_ev_list
        else:
            pid_ev_list = pid_tid_list[self.pid]
        pid_ev_list.add(self.tid)
        trace_list.append(self)
        return
    def init_common(self):
        if self.is_stack != TRACE_STACK_NOT:
            self.init_stack()
        else:
            self.init_normal()
    def __init__(self, line=""):
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
        self.kernel_stack = self
        self.user_stack = self
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

    def get_available(self):
        return self.available
    def handle(self, line):
        if self.available != TRACE_RETURN_TRUE:
            return
        if self.event_name in event_type:
            [mod_name, init_op, handle_op, event_type_list] = event_type[self.event_name]
            handle_op(line, self.priv)

def init_trace_stack():
    for te in trace_list:
        te.kernel_stack_hash = hash(str(te.kernel_stack.priv[0]))
        te.user_stack_hash = hash(str(te.user_stack.priv[0]))
        te.stack_hash = hash(str([te.kernel_stack.priv[0],te.user_stack.priv[0]]))

def init_pid_event():
    for pid in pid_tid_list:
        tid_id_list = pid_tid_list[pid]
        pid_event_list = []
        for tid in tid_id_list:
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

def parse_cpu_delay():
    for i in range(cpu_list):
        trace_list = cpu_list[i]
        index = 0
        timestamp = 0
        for te in trace_list:
            te.cpu_index = index
            te.cpu_delay = te.timestamp - timestamp
            index = index + 1
            timestamp = te.timestamp
        trace_list[0].cpu_delay = 0

def parse_tid_delay():
    for i in range(tid_list):
        trace_list = tid_list[i]
        index = 0
        timestamp = 0
        for te in trace_list:
            te.tid_index = index
            te.tid_delay = te.timestamp - timestamp
            index = index + 1
            timestamp = te.timestamp
        trace_list[0].tid_delay = 0

def parse_delay():
    parse_cpu_delay()
    parse_tid_delay()

def parse_data(data):
    data_len = len(data)
    event_type_init()
    if data_len == 0:
        return
    last_te = trace_event(data[0])
    for i in range(0, data_len):
        line = data[i]
        #print(line)
        te = trace_event(line)
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
    init_trace_stack()
    init_pid_event()
    init_stack_hash()
    parse_delay()
    return te_list

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
        if type(te.kernel_stack.priv[0])==list:
            te.kernel_stack.priv[0].reverse()
        if type(te.user_stack.priv[0])==list:
            te.user_stack.priv[0].reverse()
        print('%s\t%s\t%s\t%d, %s, %s' %(te.state, te.event_name, te.tid, te.cpu, te.kernel_stack.priv[0], te.user_stack.priv[0]))
        if type(te.kernel_stack.priv[0])==list:
            te.kernel_stack.priv[0].reverse()
        if type(te.user_stack.priv[0])==list:
            te.user_stack.priv[0].reverse()

def print_all_cpu_te(cpu_list):
    for i in range(4):
        trace_list = cpu_list[i]
        for te in trace_list:
            print(te.raw.strip())

"""
iperf  8366 [000]  1419.092642:    1000000 cpu-clock:pppH:
        ffffffff9286ee22 check_stack_object+0x82 ([kernel.kallsyms])
        ffffffff9286f233 __check_object_size+0x23 ([kernel.kallsyms])
        ffffffff931852db simple_copy_to_iter+0x2b ([kernel.kallsyms])
        ffffffff93185398 __skb_datagram_iter+0x78 ([kernel.kallsyms])
        ffffffff931856c8 skb_copy_datagram_iter+0x38 ([kernel.kallsyms])
        ffffffff93285f9e tcp_recvmsg_locked+0x2ae ([kernel.kallsyms])
        ffffffff932873b2 tcp_recvmsg+0x72 ([kernel.kallsyms])
        ffffffff932cc4b4 inet_recvmsg+0x54 ([kernel.kallsyms])
        ffffffff931690b1 sock_recvmsg+0x81 ([kernel.kallsyms])
        ffffffff9316be87 __sys_recvfrom+0xb7 ([kernel.kallsyms])
        ffffffff9316bf44 __x64_sys_recvfrom+0x24 ([kernel.kallsyms])
        ffffffff9348c1ac do_syscall_64+0x5c ([kernel.kallsyms])
        ffffffff936000aa entry_SYSCALL_64_after_hwframe+0x72 ([kernel.kallsyms])
                  12786e __libc_recv+0x6e (/usr/lib/x86_64-linux-gnu/libc.so.6)
                  12786e __libc_recv+0x6e (/usr/lib/x86_64-linux-gnu/libc.so.6)
                    cd86 [unknown] (/usr/bin/iperf)
                   25154 [unknown] (/usr/bin/iperf)
                   94b42 start_thread+0x2f2 (/usr/lib/x86_64-linux-gnu/libc.so.6)
                  1269ff __clone3+0x2f (inlined)

"""
def print_perf_te(te):
    if te.pid == "-------":
        print('%s\t0\t[00%d]\t%0.06f:\t1000\t%s:' %(te.name, te.cpu, te.timestamp, te.event_name))
    else:
        print('%s\t%s\t[00%d]\t%0.06f:\t1000\t%s:' %(te.name, te.pid, te.cpu, te.timestamp, te.event_name))
    if type(te.kernel_stack.priv[0])==list:
        for i in range(len(te.kernel_stack.priv[0])):
            stack=te.kernel_stack.priv[0][i]
            addr=te.kernel_stack.priv[1][i]
            print("\t%s %s ([kernel.kallsyms])" %(addr.strip('<').strip('>'), stack))
    if type(te.user_stack.priv[0])==list:
        for i in range(len(te.user_stack.priv[0])):
            stack=te.user_stack.priv[0][i]
            addr=te.user_stack.priv[1][i]
            print("\t%s %s (%s)" %(addr.strip('<').strip('>'), stack, te.name))
    print("")

def print_perf():
    for te in trace_list:
        print_perf_te(te)

if __name__ == '__main__':
    data = read_input(INPUT_FILE_WITH_STACK)
    te_list=parse_data(data)
    #event_stack_stat(trace_list)
    #print_all_te(trace_list)
    #print_all_te_irq(trace_list)
    #print_all_cpu_te(cpu_list)
    print_perf()
