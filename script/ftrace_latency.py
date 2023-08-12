#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Aug 16 00:19:13 2018

@author: Hao Lan
"""
import re
import pickle
import json
import time

INPUT_FTRACE_FILE = "langraph/ftrace.log"
INPUT_FTRACE_SYMBOL_FILE = "langraph/ftrace_symbol.log"
INPUT_FTRACE_FORMAT_FILE = "langraph/ftrace_format.log"
INPUT_PERF_JSON = "langraph/perf.data.json"
INPUT_PERF_SCRIPT = "langraph/perf.log"

OUTPUT_FILE = "langraph.out.json"
TRACE_FILE = "langraph.trace"

TRACE_RETURN_TRUE = 0
TRACE_RETURN_FALSE = 1
TRACE_RETURN_STACK = 2
TRACE_RETURN_COMMENT = 3
TRACE_STACK_NOT = 0
TRACE_STACK_UNDEF = 1
TRACE_STACK_KERNEL = 2
TRACE_STACK_USER = 3

"iperf   27547/27561   [001]   994.707683: cpu-clock:ppp:"
PERF_NAME_INDEX = 0
PERF_TID_INDEX = 2
PERF_PID_INDEX = 1
PERF_CPU_INDEX = 3
PERF_TIMESTAMP_INDEX = 4
PERF_EVENT_INDEX = 5
PERF_SUBEVENT_INDEX = 6
PERF_STATE_INDEX = -1
PERF_INFO_INDEX = 7
"sh-27572   (  27572) [001] d..3.   958.586575: sched_waking:"
" comm=kworker/u8:0 pid=9 prio=120 target_cpu=001"
FTRACE_NAME_INDEX = 0
FTRACE_TID_INDEX = 1
FTRACE_PID_INDEX = 2
FTRACE_CPU_INDEX = 3
FTRACE_TIMESTAMP_INDEX = 5
FTRACE_EVENT_INDEX = 6
FTRACE_SUBEVENT_INDEX = -1
FTRACE_STATE_INDEX = 4
FTRACE_INFO_INDEX = 7

NAME_INDEX = 0
TID_INDEX = 1
PID_INDEX = 2
CPU_INDEX = 3
TIMESTAMP_INDEX = 4
EVENT_INDEX = 5
SUBEVENT_INDEX = 6
STATE_INDEX = 7
INFO_INDEX = 8

DELAY_TOTAL = 0
DELAY_CPU = 1
DELAY_TID = 2
DELAY_IRQ = 3
DELAY_SOFTIRQ = 4
DELAY_MAX = 5

USER_SYMBOL_EXEC_FILE_INDEX = 2
USER_SYMBOL_ADDR_INDEX = 3
USER_SYMBOL_FUNC_NAME_INDEX = 5
USER_SYMBOL_FILE_LINE_INDEX = 7
USER_SYMBOL_SIZE = 8

LANGRAH_OUTPUT_FORMAT_CTF = 0
LANGRAH_OUTPUT_FORMAT_SVG = 1

LANGRAH_INPUT_FORMAT_FTRACE = 0
LANGRAH_INPUT_FORMAT_PERF_JSON = 1
LANGRAH_INPUT_FORMAT_PERF_SCRIPT = 2
LANGRAH_INPUT_FORMAT_EMPTY = 3


class file_opt:
    def save_variable(self, v, filename):
        f = open(filename, 'wb')
        pickle.dump(v, f)
        f.close()
        return filename

    def load_variavle(self, filename):
        f = open(filename, 'rb')
        v = pickle.load(f)
        f.close()
        return v

    def read_input(self, filename):
        f = open(filename, 'r')
        lines = f.readlines()
        f.close()
        data = list()
        for line in lines:
            if "[LOST]" in line:
                del data
                print(line)
                data = list()
            data.append(line)
        return data


"<...>-154717  ( 154717) [000] d.... 27117.357065: sched_stat_runtime: "


class trace_event_format:
    event_match = {
        "sched_kthread_stop": re.compile("comm=(.*) pid=(\d+)"),
        "sched_kthread_stop_ret": re.compile("ret=(\d+)"),
        "sched_kthread_work_execute_end": re.compile("work struct ([-+]?(0[xX])?[\dA-Fa-f]+): function (\S+)"),
        "sched_kthread_work_execute_start": re.compile("work struct ([-+]?(0[xX])?[\dA-Fa-f]+): function (\S+)"),
        "sched_kthread_work_queue_work": re.compile("work struct=([-+]?(0[xX])?[\dA-Fa-f]+) function=(\S+) worker=([-+]?(0[xX])?[\dA-Fa-f]+)"),
        "sched_migrate_task": re.compile("comm=(.*) pid=(\d+) prio=(\d+) orig_cpu=(\d+) dest_cpu=(\d+)"),
        "sched_move_numa": re.compile("pid=(\d+) tgid=(\d+) ngid=(\d+) src_cpu=(\d+) src_nid=(\d+) dst_cpu=(\d+) dst_nid=(\d+)"),
        "sched_pi_setprio": re.compile("comm=(.*) pid=(\d+) oldprio=(\d+) newprio=(\d+)"),
        "sched_process_exec": re.compile("filename=(\S+) pid=(\d+) old_pid=(\d+)"),
        "sched_process_exit": re.compile("comm=(.*) pid=(\d+) prio=(\d+)"),
        "sched_process_fork": re.compile("comm=(.*) pid=(\d+) child_comm=(.*) child_pid=(\d+)"),
        "sched_process_free": re.compile("comm=(.*) pid=(\d+) prio=(\d+)"),
        "sched_process_hang": re.compile("comm=(.*) pid=(\d+)"),
        "sched_process_wait": re.compile("comm=(.*) pid=(\d+) prio=(\d+)"),
        "sched_stat_blocked": re.compile("comm=(.*) pid=(\d+) delay=(\d+) \[ns\]"),
        "sched_stat_iowait": re.compile("comm=(.*) pid=(\d+) delay=(\d+) \[ns\]"),
        "sched_stat_runtime": re.compile("comm=(.*) pid=(\d+) runtime=(\d+) \[ns\] vruntime=(\d+) \[ns\]"),
        "sched_stat_sleep": re.compile("comm=(.*) pid=(\d+) delay=(\d+) \[ns\]"),
        "sched_stat_wait": re.compile("comm=(.*) pid=(\d+) delay=(\d+) \[ns\]"),
        "sched_stick_numa": re.compile("src_pid=(\d+) src_tgid=(\d+) src_ngid=(\d+) src_cpu=(\d+) src_nid=(\d+) dst_pid=(\d+) dst_tgid=(\d+) dst_ngid=(\d+) dst_cpu=(\d+) dst_nid=(\d+)"),
        "sched_swap_numa": re.compile("src_pid=(\d+) src_tgid=(\d+) src_ngid=(\d+) src_cpu=(\d+) src_nid=(\d+) dst_pid=(\d+) dst_tgid=(\d+) dst_ngid=(\d+) dst_cpu=(\d+) dst_nid=(\d+)"),
        "sched_switch": re.compile("prev_comm=(.*) prev_pid=(\d+) prev_prio=(\d+) prev_state=(\S+) ==> next_comm=(.*) next_pid=(\d+) next_prio=(\d+)"),
        "sched_wait_task": re.compile("comm=(.*) pid=(\d+) prio=(\d+)"),
        "sched_wake_idle_without_ipi": re.compile("cpu=(\d+)"),
        "sched_wakeup": re.compile("comm=(.*) pid=(\d+) prio=(\d+) target_cpu=(\d+)"),
        "sched_wakeup_new": re.compile("comm=(.*) pid=(\d+) prio=(\d+) target_cpu=(\d+)"),
        "sched_waking": re.compile("comm=(.*) pid=(\d+) prio=(\d+) target_cpu=(\d+)"),
        "irq_handler_entry": re.compile("irq=(\d+) name=(\S+)"),
        "irq_handler_exit": re.compile("irq=(\d+) ret=(\S+)"),
        "softirq_entry": re.compile("vec=(\d+) \[action=(\S+)\]"),
        "softirq_exit": re.compile("vec=(\d+) \[action=(\S+)\]"),
        "softirq_raise": re.compile("vec=(\d+) \[action=(\S+)\]"),
        "perf_script": re.compile("(.*) * (-*\d+)\/(-*\d+) *\[(\d+)\] *(\d+\.\d+): *(\S+):(\S+):*"),
        "ftrace": re.compile("(.{16})\-(\d+) *\( *(\S+)\) *\[(\d+)\] *(\S+) *(\S+): *(\S+)"),
    }

    def unknwon_type(self, event_name, line):
        return

    def format_event(self, event_name, line):
        if event_name not in self.event_match:
            return self.unknwon_type(event_name, line)
        pattern = self.event_match[event_name]
        match = pattern.match(line)
        if match is not None:
            return match.groups()
        else:
            print(event_name, line)
            return

    def format_head(self, format_type, line):
        if format_type == LANGRAH_INPUT_FORMAT_FTRACE:
            event_name = 'ftrace'
        elif format_type == LANGRAH_INPUT_FORMAT_PERF_SCRIPT:
            event_name = 'perf_script'
        elif format_type == LANGRAH_INPUT_FORMAT_PERF_JSON:
            event_name = 'perf_json'
        else:
            return
        if event_name in self.event_match:
            pattern = self.event_match[event_name]
            match = pattern.match(line)
            if match is not None:
                (start, end) = match.span()
                info = line[end: -1].strip()
                result = list(match.groups())
                result.append(info)
                return result
        print(format_type, line)
        return

    def parse_user_symbol(self, line):
        word = line.split()
        if len(word) != USER_SYMBOL_SIZE:
            return
        exec_file = word[USER_SYMBOL_EXEC_FILE_INDEX]
        function_addr = word[USER_SYMBOL_ADDR_INDEX]
        function_name = word[USER_SYMBOL_FUNC_NAME_INDEX]
        if "??" in function_name:
            function_name = "user_symbol_" + exec_file.split('/')[-1]
        user_symbol_index = "%s[+%s]" % (exec_file, function_addr)
        self.db.user_symbol_list[user_symbol_index] = [
            function_name, function_addr]


class trace_event:
    format_event_index = {
        LANGRAH_INPUT_FORMAT_FTRACE: [
            FTRACE_NAME_INDEX,
            FTRACE_TID_INDEX,
            FTRACE_PID_INDEX,
            FTRACE_CPU_INDEX,
            FTRACE_TIMESTAMP_INDEX,
            FTRACE_EVENT_INDEX,
            FTRACE_SUBEVENT_INDEX,
            FTRACE_STATE_INDEX,
            FTRACE_INFO_INDEX,
        ],
        LANGRAH_INPUT_FORMAT_PERF_SCRIPT: [
            PERF_NAME_INDEX,
            PERF_TID_INDEX,
            PERF_PID_INDEX,
            PERF_CPU_INDEX,
            PERF_TIMESTAMP_INDEX,
            PERF_EVENT_INDEX,
            PERF_SUBEVENT_INDEX,
            PERF_STATE_INDEX,
            PERF_INFO_INDEX,
        ]
    }

    def perf_json_stack(self, te_json={}):
        [stack_name_list, stack_addr_list] = self.kernel_stack
        [ustack_name_list, ustack_addr_list] = self.user_stack
        for callchain in te_json['callchain']:
            if int(callchain['ip'], 16) > 0xf000000000000000:
                if 'ip' in callchain:
                    stack_name_list.append(callchain['ip'])
                if 'symbol' in callchain:
                    stack_addr_list.append(callchain['symbol'])
            else:
                if 'ip' in callchain:
                    ustack_name_list.append(callchain['ip'])
                if 'symbol' in callchain:
                    ustack_addr_list.append(callchain['symbol'])

    def perf_json_event(self, te_json):
        self.raw = te_json
        self.available = TRACE_RETURN_TRUE
        self.name = te_json['comm']
        self.tid = te_json['tid']
        self.pid = te_json['pid']
        self.cpu = int(te_json['cpu'])
        self.timestamp = te_json['timestamp']
        self.event_name = "cpu-clock"
        self.perf_json_stack(te_json)

    pid_valid = re.compile("\d+")

    def fixed_pid_tid(self):
        if self.pid_valid.match(self.pid) is not None:
            self.pid = int(self.pid)
        else:
            self.pid = int(0)
        if self.pid_valid.match(self.tid) is not None:
            self.tid = int(self.tid)
        else:
            self.tid = int(0)

    def parse_event(self, line):
        head = self.format.format_head(self.format_type, line)
        if head is None:
            self.available = TRACE_RETURN_FALSE
            return
        index = self.format_event_index[self.format_type]
        self.name = head[index[NAME_INDEX]].strip()
        self.tid = head[index[TID_INDEX]]
        self.pid = head[index[PID_INDEX]]
        self.fixed_pid_tid()
        self.cpu = int(head[index[CPU_INDEX]])
        if index[STATE_INDEX] != -1:
            self.state = head[index[STATE_INDEX]]
        self.timestamp = int(head[index[TIMESTAMP_INDEX]].replace('.', ''))
        if index[SUBEVENT_INDEX] != -1:
            self.event_name = head[index[EVENT_INDEX]].strip(':')
        else:
            # TODO do not think about perf event
            self.event_name = head[index[EVENT_INDEX]].strip(':')
        info = head[-1]
        match = self.format.format_event(self.event_name, info)
        if match is not None:
            self.priv = match
        else:
            self.priv = info

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
        self.parse_event(line)

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
        self.parse_event(line)

    def alloc_event(self):
        self.raw = self
        self.available = TRACE_RETURN_FALSE
        self.is_stack = TRACE_STACK_NOT
        self.kernel_stack = [[], []]
        self.user_stack = [[], []]
        self.kernel_stack_hash = int(0)
        self.user_stack_hash = int(0)
        self.stack_hash = int(0)
        self.delay = [int(0)] * DELAY_MAX
        self.index = [int(0)] * DELAY_MAX
        self.period = {}
        self.name = str()
        self.tid = int(0)
        self.pid = int(0)
        self.cpu = int(0)
        self.state = str()
        self.timestamp = int(0)
        self.event_name = str()

    def __init__(self, line, format_type, event_format):
        '''print(line, format_type)'''
        self.alloc_event()
        self.format = event_format
        self.format_type = format_type
        if format_type == LANGRAH_INPUT_FORMAT_FTRACE:
            self.ftrace_event(line)
        elif format_type == LANGRAH_INPUT_FORMAT_PERF_SCRIPT:
            self.perf_script_event(line)
        elif format_type == LANGRAH_INPUT_FORMAT_PERF_JSON:
            self.perf_json_event(line)

    def get_available(self):
        return self.available


class trace_event_json:
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

        def format_pidname_metadata(self, name, pid, tid):
            self.name = "process_name"
            self.args['name'] = name
            self.pid = pid
            self.tid = tid
            self.ts = int(0)
            self.cat = '__metadata'
            self.ph = "M"

        def format_tidname_metadata(self, name, pid, tid):
            self.name = "thread_name"
            self.args['name'] = name
            self.pid = pid
            self.tid = tid
            self.ts = int(0)
            self.cat = '__metadata'
            self.ph = "M"

    def get_trace_event_format(self):
        return self.json_tree

    def clean_trace_event_format(self):
        self.json_tree = {}
        self.json_tree['traceEvents'] = list()
        self.json_tree_result = [self.json_tree]

    def save_trace_event_format(self, output=OUTPUT_FILE):
        fd = open(output, 'w+')
        fd.write(json.dumps(self.json_tree_result, indent=0))

    def __init__(self):
        self.clean_trace_event_format()

    def insert_item(self, item):
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

    def alloc_item(self):
        return self.trace_event_json_item()


class trace_event_database:
    class event_opt:
        def ftrace_insert_stack(self, line, priv):
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

        def perf_insert_stack(self, line, priv):
            [[stack_name_list, stack_addr_list],
             [ustack_name_list, ustack_addr_list]] = priv
            key_word = line.split()
            key_word_len = len(key_word)
            if key_word_len > 1:
                if int(key_word[0], 16) > 0xf000000000000000:
                    stack_name_list.append(key_word[1])
                    stack_addr_list.append(key_word[0])
                else:
                    ustack_name_list.append(key_word[1])
                    ustack_addr_list.append(key_word[0])
            elif key_word_len == 1:
                if int(key_word[0], 16) > 0xf000000000000000:
                    stack_name_list.append(key_word[0])
                    stack_addr_list.append(key_word[0])
                else:
                    ustack_name_list.append(key_word[0])
                    ustack_addr_list.append(key_word[0])
            else:
                print("Error stack "+line)

        def null_pre_init(self, ev):
            return

        def perf_pre_init(self, ev):
            ev.priv = [ev.kernel_stack, ev.user_stack]
            return

        def ftrace_stack_pre_init(self, ev):
            ev.priv = [[], []]
            if ev.event_name == "<stack":
                ev.is_stack = TRACE_STACK_KERNEL
            else:
                ev.is_stack = TRACE_STACK_USER
            return

        def irq_pre_init(self, ev):
            irq_info = ev.priv
            irq_num = irq_info[0]
            if irq_num not in self.db.irq_list:
                irq_ev_list = []
                self.db.irq_list[irq_num] = irq_ev_list
            else:
                irq_ev_list = self.db.irq_list[irq_num]
            irq_ev_list.append(ev)
            return

        def softirq_pre_init(self, ev):
            vec_info = ev.priv
            vec_num = vec_info[0]
            if vec_num not in self.db.vec_list:
                vec_ev_list = []
                self.db.vec_list[vec_num] = vec_ev_list
            else:
                vec_ev_list = self.db.vec_list[vec_num]
            vec_ev_list.append(ev)
            return

        def null_insert_stack(self, line, priv):
            return

        def null_timeline(self, ev):
            return

        def null_insert_cpu(self, ev):
            return

        def __init__(self, database, mod_name='', pre_init_opt=null_pre_init,
                     insert_stack_opt=null_insert_stack,
                     timeline_opt=null_timeline,
                     insert_cpu_opt=null_insert_cpu):
            self.mod_name = mod_name
            self.pre_init_opt = pre_init_opt
            self.insert_stack_opt = insert_stack_opt
            self.timeline_opt = timeline_opt
            self.insert_cpu_opt = insert_cpu_opt
            self.db = database

    class pre_processing:
        def insert_stack(self, te, line):
            if te.available != TRACE_RETURN_TRUE:
                return
            if te.event_name in self.db.event_type:
                opt = self.db.event_type[te.event_name]
                opt.insert_stack_opt(self, line, te.priv)

        def pre_init(self, te, line):
            if te.available != TRACE_RETURN_TRUE:
                return
            if te.event_name in self.db.event_type:
                opt = self.db.event_type[te.event_name]
                opt.pre_init_opt(self, te)

        def insert_dict_list(self, te, key, ev_dict_list):
            if key not in ev_dict_list:
                ev_list = []
                ev_dict_list[key] = ev_list
            else:
                ev_list = ev_dict_list[key]
            ev_list.append(te)

        def insert_tid_pid_list(self, te):
            if te.pid not in self.db.pid_tid_list:
                pid_ev_list = dict()
                self.db.pid_tid_list[te.pid] = pid_ev_list
                pid_ev_list["name"] = ""
            else:
                pid_ev_list = self.db.pid_tid_list[te.pid]
            if te.pid == te.tid:
                pid_ev_list["name"] = te.name

        def init_stack(self, te):
            if te.cpu not in self.db.cpu_list:
                return
            else:
                cpu_ev_list = self.db.cpu_list[te.cpu]
            if len(cpu_ev_list) == 0:
                return
            cpu_ev = cpu_ev_list[-1]
            if te.is_stack == TRACE_STACK_KERNEL:
                cpu_ev.kernel_stack = te.priv[:]
            else:
                cpu_ev.user_stack = te.priv[:]
            return

        def init_normal(self, te):
            self.insert_dict_list(te, te.cpu, self.db.cpu_list)
            self.insert_dict_list(te, te.tid, self.db.tid_list)
            self.insert_dict_list(te, te.event_name, self.db.event_mod_list)
            self.db.trace_list.append(te)
            return

        def init_common(self, te):
            if te.is_stack != TRACE_STACK_NOT:
                self.init_stack(te)
            else:
                self.init_normal(te)

        def parse_data(self, data, format_type=LANGRAH_INPUT_FORMAT_FTRACE):
            data_len = len(data)
            if data_len == 0:
                return
            event_format = trace_event_format()
            last_te = trace_event('', LANGRAH_INPUT_FORMAT_EMPTY, event_format)
            for i in range(0, data_len):
                line = data[i]
                # print(line)
                te = trace_event(line, format_type, event_format)
                if te.get_available() == TRACE_RETURN_FALSE:
                    print(data[i], "TRACE_RETURN_FALSE")
                    continue
                if te.get_available() == TRACE_RETURN_COMMENT:
                    continue
                if te.get_available() == TRACE_RETURN_STACK:
                    if last_te.get_available() == TRACE_RETURN_TRUE:
                        self.insert_stack(last_te, line)
                        continue
                    else:
                        print(data[i], "TRACE_RETURN_FALSE")
                        continue
                last_te = te
                self.pre_init(te, line)
                self.init_common(te)
                self.db.te_list.append(te)

        def parse_perf_json(self, input_filename=INPUT_PERF_JSON):
            fd = open(input_filename)
            json_data = json.load(fd)
            fmt = trace_event_format()
            for json_te in json_data['samples']:
                te = trace_event(json_te, LANGRAH_INPUT_FORMAT_PERF_JSON, fmt)
                if te.get_available() == TRACE_RETURN_FALSE:
                    print("TRACE_RETURN_FALSE")
                    continue
                self.db.te_list.append(te)
                self.pre_init(te, json_te)
                self.init_normal(te)
            fd.close()
            del json_data

        def __init__(self, database):
            self.db = database

    class post_processing:
        def __init__(self, database, output_format):
            self.output = trace_event_json()
            self.db = database

        def format_thread_name_metadata(self):
            for pid in self.db.pid_tid_list:
                tid_id_list = self.db.pid_tid_list[pid]
                for tid in tid_id_list:
                    pid_name = tid_id_list[tid]
                    item = self.output.alloc_item()
                    if tid != "name":
                        item.format_tidname_metadata(pid_name, pid, tid)
                    else:
                        item.format_pidname_metadata(pid_name, pid, pid)
                    self.output.insert_item(item)

    class analysis:
        def get_irq_name(self, event_name, irq_ev):
            (irq_num, irq_name) = irq_ev[0].priv
            for ev in irq_ev:
                if event_name == ev.event_name:
                    (irq_num, irq_name) = ev.priv
                    return irq_name
            return irq_name

        def irq_to_thread_name(self, irq_list_name,
                               event_name, pid_cur, irq_ev_list):
            irq_pid_list = {'name': irq_list_name}
            irq_pid_max = pid_cur
            for irq_id in irq_ev_list.keys():
                irq_pid = pid_cur + int(irq_id)
                irq_pid_max = max(irq_pid_max, irq_pid)
                irq_name = self.get_irq_name(event_name, irq_ev_list[irq_id])
                irq_pid_list[irq_pid] = irq_name
            self.db.pid_tid_list[pid_cur] = irq_pid_list
            return irq_pid_max

        def cpu_to_thread_name(self, cpu_list_name, pid_cur, cpu_ev_list):
            cpu_pid_list = {'name': cpu_list_name}
            cpu_pid_max = pid_cur
            for cpu_id in cpu_ev_list.keys():
                cpu_pid = pid_cur + int(cpu_id)
                cpu_pid_max = max(cpu_pid_max, cpu_pid)
                cpu_name = cpu_list_name+'_'+str(cpu_id)
                cpu_pid_list[cpu_pid] = cpu_name
            self.db.pid_tid_list[pid_cur] = cpu_pid_list
            return cpu_pid_max

        def get_max_tid(self):
            pid_name_list = list()
            for pid in self.db.pid_tid_list:
                tid_id_list = self.db.pid_tid_list[pid]
                for tid in tid_id_list:
                    if tid == "name":
                        continue
                    pid_name_list.append(tid)
            return max(pid_name_list)

        def init_metadata_event(self):
            pid_cur = self.get_max_tid() + 1
            self.db.cpu_tid = pid_cur
            pid_cur = self.cpu_to_thread_name("langrah_cpu",
                                              pid_cur, self.db.cpu_list) + 1
            self.db.irq_tid = pid_cur
            pid_cur = self.irq_to_thread_name("langrah_irq",
                                              'irq_handler_entry',
                                              pid_cur, self.db.irq_list) + 1
            self.db.vec_tid = pid_cur
            pid_cur = self.irq_to_thread_name("langrah_softirq",
                                              'softirq_entry',
                                              pid_cur, self.db.vec_list)

        def init_trace_stack(self):
            for te in self.db.trace_list:
                te.kernel_stack_hash = hash(str(te.kernel_stack[0]))
                te.user_stack_hash = hash(str(te.user_stack[0]))
                te.stack_hash = hash(
                    str([te.kernel_stack[0], te.user_stack[0]]))

        def init_pid_event(self):
            for pid in self.db.pid_tid_list:
                tid_id_list = self.db.pid_tid_list[pid]
                pid_event_list = []
                for tid in tid_id_list:
                    if tid == "name":
                        continue
                    pid_event_list.extend(self.db.tid_list[tid])
                pid_event_list.sort(key=lambda x: x.timestamp)
                self.db.pid_list[pid] = pid_event_list

        def init_stack_hash(self):
            for te in self.db.trace_list:
                hash_id = te.stack_hash
                if hash_id in self.db.stack_hash_list:
                    hash_num = self.db.stack_hash_list[hash_id]
                    self.db.stack_hash_list[hash_id] = hash_num + 1
                else:
                    self.db.stack_hash_list[hash_id] = 1

        def parse_delay_list(self, delay_list, delay_offset):
            for ev in delay_list.values():
                index = int(0)
                timestamp = self.db.timestamp_start
                for te in ev:
                    te.index[delay_offset] = index
                    te.delay[delay_offset] = te.timestamp - timestamp
                    index = index + 1
                    timestamp = te.timestamp

        def parse_delay(self):
            self.parse_delay_list(self.db.tid_list, DELAY_TID)
            self.parse_delay_list(self.db.cpu_list, DELAY_CPU)
            self.parse_delay_list(self.db.vec_list, DELAY_SOFTIRQ)
            self.parse_delay_list(self.db.irq_list, DELAY_IRQ)

        def init_list(self, ls):
            if type(ls) != dict:
                return
            for evlist in ls.values():
                if type(evlist) == list:
                    evlist.sort(key=lambda x: x.timestamp)

        def init_global(self):
            self.db.trace_list.sort(key=lambda x: x.timestamp)
            self.init_list(self.db.cpu_list)
            self.init_list(self.db.irq_list)
            self.init_list(self.db.tid_list)
            self.init_list(self.db.vec_list)
            self.init_trace_stack()
            self.init_stack_hash()
            self.db.timestamp_start = self.db.trace_list[0].timestamp
            self.db.timestamp_end = self.db.trace_list[-1].timestamp
            self.parse_delay()
            self.init_metadata_event()

        def event_type_priv_max(self, event="<user stack trace>"):
            if event not in self.db.event_type:
                print("Event %s not in event_type." % event)
                return
            opt = self.db.event_type[event]
            max_size = 0
            for ev in opt.event_type_list:
                if max_size < len(ev.priv):
                    max_size = len(ev.priv)
            print("%s max_size is %d." % (event, max_size))

        def event_type_print_priv(self):
            for name in self.db.event_type:
                opt = self.db.event_type[name]
                if len(opt.event_type_list) != 0:
                    print(name, opt.event_type_list[0].priv)
                else:
                    print(name)

        def print_all_te(self, trace_list):
            for te in trace_list:
                print('%d\t%08X %s %s|%s' % (
                    self.db.stack_hash_list[te.stack_hash], abs(
                        te.stack_hash), te.raw.strip(),
                    te.kernel_stack.priv[0],
                    te.user_stack.priv[0]))

        def __init__(self, database):
            self.db = database

    def alloc_resource(self):
        self.cpu_list = {}
        self.tid_list = {}
        self.irq_list = {}
        self.vec_list = {}
        self.trace_list = []
        self.pid_list = {}
        self.event_mod_list = {}
        self.pid_tid_list = {}
        self.te_list = []
        self.stack_hash_list = {}
        self.user_symbol_list = {}
        self.timestamp_start = -1.0
        self.timestamp_end = -1.0
        self.irq_tid = int(0)
        self.vec_tid = int(0)
        self.cpu_tid = int(0)

    def init_event_type(self):
        self.event_type = {
            "sched_kthread_stop": self.event_opt(self, "sched"),
            "sched_kthread_stop_ret": self.event_opt(self, "sched"),
            "sched_kthread_work_execute_end": self.event_opt(self, "sched"),
            "sched_kthread_work_execute_start": self.event_opt(self, "sched"),
            "sched_kthread_work_queue_work": self.event_opt(self, "sched"),
            "sched_migrate_task": self.event_opt(self, "sched"),
            "sched_move_numa": self.event_opt(self, "sched"),
            "sched_pi_setprio": self.event_opt(self, "sched"),
            "sched_process_exec": self.event_opt(self, "sched"),
            "sched_process_exit": self.event_opt(self, "sched"),
            "sched_process_fork": self.event_opt(self, "sched"),
            "sched_process_free": self.event_opt(self, "sched"),
            "sched_process_hang": self.event_opt(self, "sched"),
            "sched_process_wait": self.event_opt(self, "sched"),
            "sched_stat_blocked": self.event_opt(self, "sched"),
            "sched_stat_iowait": self.event_opt(self, "sched"),
            "sched_stat_runtime": self.event_opt(self, "sched"),
            "sched_stat_sleep": self.event_opt(self, "sched"),
            "sched_stat_wait": self.event_opt(self, "sched"),
            "sched_stick_numa": self.event_opt(self, "sched"),
            "sched_swap_numa": self.event_opt(self, "sched"),
            "sched_switch": self.event_opt(self, "sched"),
            "sched_wait_task": self.event_opt(self, "sched"),
            "sched_wake_idle_without_ipi": self.event_opt(self, "sched"),
            "sched_wakeup": self.event_opt(self, "sched"),
            "sched_wakeup_new": self.event_opt(self, "sched"),
            "sched_waking": self.event_opt(self, "sched"),
            "irq_handler_entry": self.event_opt(self, "irq",
                                                self.event_opt.irq_pre_init),
            "irq_handler_exit": self.event_opt(self, "irq",
                                               self.event_opt.irq_pre_init),
            "softirq_entry": self.event_opt(self, "irq",
                                            self.event_opt.softirq_pre_init),
            "softirq_exit": self.event_opt(self, "irq",
                                           self.event_opt.softirq_pre_init),
            "softirq_raise": self.event_opt(self, "irq",
                                            self.event_opt.softirq_pre_init),
            "<stack": self.event_opt(self, "ftrace",
                                     self.event_opt.ftrace_stack_pre_init,
                                     self.event_opt.ftrace_insert_stack),
            "<user":
                self.event_opt(self, "ftrace",
                               self.event_opt.ftrace_stack_pre_init,
                               self.event_opt.ftrace_insert_stack),
            "cpu-clock": self.event_opt(self, "perf",
                                        self.event_opt.perf_pre_init,
                                        self.event_opt.perf_insert_stack),
            "cpu-cycles": self.event_opt(self, "perf",
                                         self.event_opt.perf_pre_init,
                                         self.event_opt.perf_insert_stack),
        }

    def get_handle(self, event_name):
        if event_name in self.event_type:
            return self.event_type[event_name]
        return

    def __init__(self):
        self.event_opts = self.event_opt(self)
        self.pre_opts = self.pre_processing(self)
        self.post_opts = self.post_processing(self, LANGRAH_OUTPUT_FORMAT_CTF)
        self.anly = self.analysis(self)
        self.alloc_resource()
        self.init_event_type()


class debug:
    def event_check_stack(self, data, te_list):
        te_len = len(te_list)
        for i in range(te_len):
            if te_list[i].event_name == "<stack trace>" and \
                    te_list[i].event_name != "<user stack trace>":
                print(te_list[i].timestamp)

    def event_stack_stat(self, te_list):
        te_len = len(te_list)
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

    def print_all_te_irq(self, trace_list):
        for te in trace_list:
            if len(te.kernel_stack[0]) > 0:
                te.kernel_stack[0].reverse()
            if len(te.user_stack[0]) > 0:
                te.user_stack[0].reverse()
            print('%s\t%s\t%s\t%d, %s, %s' % (te.state, te.event_name,
                  te.tid, te.cpu, te.kernel_stack[0], te.user_stack[0]))
            if len(te.kernel_stack[0]) > 0:
                te.kernel_stack[0].reverse()
            if len(te.user_stack[0]) > 0:
                te.user_stack[0].reverse()

    def print_all_cpu_te(self, cpu_list):
        for i in range(4):
            trace_list = cpu_list[i]
            for te in trace_list:
                print(te.raw.strip())

    def print_all_time(self, stat_t):
        for i in range(len(stat_t) - 1):
            print(stat_t[i + 1]-stat_t[i])

    def print_time(self, stat_t):
        stat_t.append(time.perf_counter())
        print(stat_t[len(stat_t) - 1]-stat_t[-2])


class event_to_perf:
    def print_evnt(self, te):
        if te.pid == "-------":
            print('%s\t0\t[00%d]\t%0.06f:\t1000\t%s:' %
                  (te.name, te.cpu, te.timestamp, te.event_name))
        else:
            print('%s\t%s\t[00%d]\t%0.06f:\t1000\t%s:' %
                  (te.name, te.pid, te.cpu, te.timestamp, te.event_name))
        if len(te.kernel_stack[0]) > 0:
            for i in range(len(te.kernel_stack[0])):
                stack = te.kernel_stack[0][i]
                addr = te.kernel_stack[1][i]
                print("\t%s %s ([kernel.kallsyms])" %
                      (addr.strip('<').strip('>'), stack))
        if len(te.user_stack[0]) > 0:
            for i in range(len(te.user_stack[0])):
                stack = te.user_stack[0][i]
                addr = te.user_stack[1][i]
                print("\t%s %s (%s)" % (addr.strip('<').strip('>'),
                                        stack, te.name))
        print("")

    def conver_to_perf(self, trace_list):
        for te in trace_list:
            event_to_perf(te)


if __name__ == '__main__':
    db = trace_event_database()
    file_opts = file_opt()
    debug_opts = debug()
    stat_t = [time.perf_counter()]
    data = file_opts.read_input(INPUT_FTRACE_FILE)
    debug_opts.print_time(stat_t)
    db.pre_opts.parse_data(
        data, format_type=LANGRAH_INPUT_FORMAT_FTRACE)
    debug_opts.print_time(stat_t)
    data = file_opts.read_input(INPUT_PERF_SCRIPT)
    debug_opts.print_time(stat_t)
    db.pre_opts.parse_data(
        data, format_type=LANGRAH_INPUT_FORMAT_PERF_SCRIPT)
    debug_opts.print_time(stat_t)
    db.anly.init_global()
    debug_opts.print_time(stat_t)
    # event_stack_stat(trace_list)
    # print_all_te(trace_list)
    # print_all_te_irq(trace_list)
    # print_all_cpu_te(cpu_list)
