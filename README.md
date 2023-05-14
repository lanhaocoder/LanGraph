# LanGraph
Latency Graph for linux ftrace scheduler latency analysis,base on trace-cmd.

support evnet:

/sys/kernel/debug/tracing/events/sched/
sched_kthread_stop
sched_kthread_stop_ret
sched_kthread_work_execute_end
sched_kthread_work_execute_start
sched_kthread_work_queue_work
sched_migrate_task
sched_move_numa
sched_pi_setprio
sched_process_exec
sched_process_exit
sched_process_fork
sched_process_free
sched_process_hang
sched_process_wait
sched_stat_blocked
sched_stat_iowait
sched_stat_runtime
sched_stat_sleep
sched_stat_wait
sched_stick_numa
sched_swap_numa
sched_switch
sched_wait_task
sched_wake_idle_without_ipi
sched_wakeup
sched_wakeup_new
sched_waking

/sys/kernel/debug/tracing/events/irq
irq_handler_entry
irq_handler_exit
softirq_entry
softirq_exit
softirq_raise

cat /sys/kernel/debug/tracing/events/sched/*/format
name: sched_kthread_stop
ID: 326
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;

print fmt: "comm=%s pid=%d", REC->comm, REC->pid
name: sched_kthread_stop_ret
ID: 325
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:int ret;  offset:8;       size:4; signed:1;

print fmt: "ret=%d", REC->ret
name: sched_kthread_work_execute_end
ID: 322
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:void * work;      offset:8;       size:8; signed:0;
        field:void * function;  offset:16;      size:8; signed:0;

print fmt: "work struct %p: function %ps", REC->work, REC->function
name: sched_kthread_work_execute_start
ID: 323
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:void * work;      offset:8;       size:8; signed:0;
        field:void * function;  offset:16;      size:8; signed:0;

print fmt: "work struct %p: function %ps", REC->work, REC->function
name: sched_kthread_work_queue_work
ID: 324
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:void * work;      offset:8;       size:8; signed:0;
        field:void * function;  offset:16;      size:8; signed:0;
        field:void * worker;    offset:24;      size:8; signed:0;

print fmt: "work struct=%p function=%ps worker=%p", REC->work, REC->function, REC->worker
name: sched_migrate_task
ID: 317
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:int prio; offset:28;      size:4; signed:1;
        field:int orig_cpu;     offset:32;      size:4; signed:1;
        field:int dest_cpu;     offset:36;      size:4; signed:1;

print fmt: "comm=%s pid=%d prio=%d orig_cpu=%d dest_cpu=%d", REC->comm, REC->pid, REC->prio, REC->orig_cpu, REC->dest_cpu
name: sched_move_numa
ID: 303
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:pid_t pid;        offset:8;       size:4; signed:1;
        field:pid_t tgid;       offset:12;      size:4; signed:1;
        field:pid_t ngid;       offset:16;      size:4; signed:1;
        field:int src_cpu;      offset:20;      size:4; signed:1;
        field:int src_nid;      offset:24;      size:4; signed:1;
        field:int dst_cpu;      offset:28;      size:4; signed:1;
        field:int dst_nid;      offset:32;      size:4; signed:1;

print fmt: "pid=%d tgid=%d ngid=%d src_cpu=%d src_nid=%d dst_cpu=%d dst_nid=%d", REC->pid, REC->tgid, REC->ngid, REC->src_cpu, REC->src_nid, REC->dst_cpu, REC->dst_nid
name: sched_pi_setprio
ID: 305
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:int oldprio;      offset:28;      size:4; signed:1;
        field:int newprio;      offset:32;      size:4; signed:1;

print fmt: "comm=%s pid=%d oldprio=%d newprio=%d", REC->comm, REC->pid, REC->oldprio, REC->newprio
name: sched_process_exec
ID: 311
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:__data_loc char[] filename;       offset:8;       size:4; signed:1;
        field:pid_t pid;        offset:12;      size:4; signed:1;
        field:pid_t old_pid;    offset:16;      size:4; signed:1;

print fmt: "filename=%s pid=%d old_pid=%d", __get_str(filename), REC->pid, REC->old_pid
name: sched_process_exit
ID: 315
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:int prio; offset:28;      size:4; signed:1;

print fmt: "comm=%s pid=%d prio=%d", REC->comm, REC->pid, REC->prio
name: sched_process_fork
ID: 312
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char parent_comm[16];     offset:8;       size:16;        signed:1;
        field:pid_t parent_pid; offset:24;      size:4; signed:1;
        field:char child_comm[16];      offset:28;      size:16;        signed:1;
        field:pid_t child_pid;  offset:44;      size:4; signed:1;

print fmt: "comm=%s pid=%d child_comm=%s child_pid=%d", REC->parent_comm, REC->parent_pid, REC->child_comm, REC->child_pid
name: sched_process_free
ID: 316
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:int prio; offset:28;      size:4; signed:1;

print fmt: "comm=%s pid=%d prio=%d", REC->comm, REC->pid, REC->prio
name: sched_process_hang
ID: 304
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;

print fmt: "comm=%s pid=%d", REC->comm, REC->pid
name: sched_process_wait
ID: 313
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:int prio; offset:28;      size:4; signed:1;

print fmt: "comm=%s pid=%d prio=%d", REC->comm, REC->pid, REC->prio
name: sched_stat_blocked
ID: 307
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:u64 delay;        offset:32;      size:8; signed:0;

print fmt: "comm=%s pid=%d delay=%Lu [ns]", REC->comm, REC->pid, (unsigned long long)REC->delay
name: sched_stat_iowait
ID: 308
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:u64 delay;        offset:32;      size:8; signed:0;

print fmt: "comm=%s pid=%d delay=%Lu [ns]", REC->comm, REC->pid, (unsigned long long)REC->delay
name: sched_stat_runtime
ID: 306
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:u64 runtime;      offset:32;      size:8; signed:0;
        field:u64 vruntime;     offset:40;      size:8; signed:0;

print fmt: "comm=%s pid=%d runtime=%Lu [ns] vruntime=%Lu [ns]", REC->comm, REC->pid, (unsigned long long)REC->runtime, (unsigned long long)REC->vruntime
name: sched_stat_sleep
ID: 309
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:u64 delay;        offset:32;      size:8; signed:0;

print fmt: "comm=%s pid=%d delay=%Lu [ns]", REC->comm, REC->pid, (unsigned long long)REC->delay
name: sched_stat_wait
ID: 310
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:u64 delay;        offset:32;      size:8; signed:0;

print fmt: "comm=%s pid=%d delay=%Lu [ns]", REC->comm, REC->pid, (unsigned long long)REC->delay
name: sched_stick_numa
ID: 302
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:pid_t src_pid;    offset:8;       size:4; signed:1;
        field:pid_t src_tgid;   offset:12;      size:4; signed:1;
        field:pid_t src_ngid;   offset:16;      size:4; signed:1;
        field:int src_cpu;      offset:20;      size:4; signed:1;
        field:int src_nid;      offset:24;      size:4; signed:1;
        field:pid_t dst_pid;    offset:28;      size:4; signed:1;
        field:pid_t dst_tgid;   offset:32;      size:4; signed:1;
        field:pid_t dst_ngid;   offset:36;      size:4; signed:1;
        field:int dst_cpu;      offset:40;      size:4; signed:1;
        field:int dst_nid;      offset:44;      size:4; signed:1;

print fmt: "src_pid=%d src_tgid=%d src_ngid=%d src_cpu=%d src_nid=%d dst_pid=%d dst_tgid=%d dst_ngid=%d dst_cpu=%d dst_nid=%d", REC->src_pid, REC->src_tgid, REC->src_ngid, REC->src_cpu, REC->src_nid, REC->dst_pid, REC->dst_tgid, REC->dst_ngid, REC->dst_cpu, REC->dst_nid
name: sched_swap_numa
ID: 301
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:pid_t src_pid;    offset:8;       size:4; signed:1;
        field:pid_t src_tgid;   offset:12;      size:4; signed:1;
        field:pid_t src_ngid;   offset:16;      size:4; signed:1;
        field:int src_cpu;      offset:20;      size:4; signed:1;
        field:int src_nid;      offset:24;      size:4; signed:1;
        field:pid_t dst_pid;    offset:28;      size:4; signed:1;
        field:pid_t dst_tgid;   offset:32;      size:4; signed:1;
        field:pid_t dst_ngid;   offset:36;      size:4; signed:1;
        field:int dst_cpu;      offset:40;      size:4; signed:1;
        field:int dst_nid;      offset:44;      size:4; signed:1;

print fmt: "src_pid=%d src_tgid=%d src_ngid=%d src_cpu=%d src_nid=%d dst_pid=%d dst_tgid=%d dst_ngid=%d dst_cpu=%d dst_nid=%d", REC->src_pid, REC->src_tgid, REC->src_ngid, REC->src_cpu, REC->src_nid, REC->dst_pid, REC->dst_tgid, REC->dst_ngid, REC->dst_cpu, REC->dst_nid
name: sched_switch
ID: 318
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char prev_comm[16];       offset:8;       size:16;        signed:1;
        field:pid_t prev_pid;   offset:24;      size:4; signed:1;
        field:int prev_prio;    offset:28;      size:4; signed:1;
        field:long prev_state;  offset:32;      size:8; signed:1;
        field:char next_comm[16];       offset:40;      size:16;        signed:1;
        field:pid_t next_pid;   offset:56;      size:4; signed:1;
        field:int next_prio;    offset:60;      size:4; signed:1;

print fmt: "prev_comm=%s prev_pid=%d prev_prio=%d prev_state=%s%s ==> next_comm=%s next_pid=%d next_prio=%d", REC->prev_comm, REC->prev_pid, REC->prev_prio, (REC->prev_state & ((((0x0000 | 0x0001 | 0x0002 | 0x0004 | 0x0008 | 0x0010 | 0x0020 | 0x0040) + 1) << 1) - 1)) ? __print_flags(REC->prev_state & ((((0x0000 | 0x0001 | 0x0002 | 0x0004 | 0x0008 | 0x0010 | 0x0020 | 0x0040) + 1) << 1) - 1), "|", { 0x0001, "S" }, { 0x0002, "D" }, { 0x0004, "T" }, { 0x0008, "t" }, { 0x0010, "X" }, { 0x0020, "Z" }, { 0x0040, "P" }, { 0x0080, "I" }) : "R", REC->prev_state & (((0x0000 | 0x0001 | 0x0002 | 0x0004 | 0x0008 | 0x0010 | 0x0020 | 0x0040) + 1) << 1) ? "+" : "", REC->next_comm, REC->next_pid, REC->next_prio
name: sched_wait_task
ID: 314
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:int prio; offset:28;      size:4; signed:1;

print fmt: "comm=%s pid=%d prio=%d", REC->comm, REC->pid, REC->prio
name: sched_wake_idle_without_ipi
ID: 300
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:int cpu;  offset:8;       size:4; signed:1;

print fmt: "cpu=%d", REC->cpu
name: sched_wakeup
ID: 320
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:int prio; offset:28;      size:4; signed:1;
        field:int target_cpu;   offset:32;      size:4; signed:1;

print fmt: "comm=%s pid=%d prio=%d target_cpu=%03d", REC->comm, REC->pid, REC->prio, REC->target_cpu
name: sched_wakeup_new
ID: 319
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:int prio; offset:28;      size:4; signed:1;
        field:int target_cpu;   offset:32;      size:4; signed:1;

print fmt: "comm=%s pid=%d prio=%d target_cpu=%03d", REC->comm, REC->pid, REC->prio, REC->target_cpu
name: sched_waking
ID: 321
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:char comm[16];    offset:8;       size:16;        signed:1;
        field:pid_t pid;        offset:24;      size:4; signed:1;
        field:int prio; offset:28;      size:4; signed:1;
        field:int target_cpu;   offset:32;      size:4; signed:1;

print fmt: "comm=%s pid=%d prio=%d target_cpu=%03d", REC->comm, REC->pid, REC->prio, REC->target_cpu
root@lanhao-VirtualBox:/home/lanhao# cat /sys/kernel/debug/tracing/events/irq/*/format
name: irq_handler_entry
ID: 151
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:int irq;  offset:8;       size:4; signed:1;
        field:__data_loc char[] name;   offset:12;      size:4; signed:1;

print fmt: "irq=%d name=%s", REC->irq, __get_str(name)
name: irq_handler_exit
ID: 150
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:int irq;  offset:8;       size:4; signed:1;
        field:int ret;  offset:12;      size:4; signed:1;

print fmt: "irq=%d ret=%s", REC->irq, REC->ret ? "handled" : "unhandled"
name: softirq_entry
ID: 149
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:unsigned int vec; offset:8;       size:4; signed:0;

print fmt: "vec=%u [action=%s]", REC->vec, __print_symbolic(REC->vec, { 0, "HI" }, { 1, "TIMER" }, { 2, "NET_TX" }, { 3, "NET_RX" }, { 4, "BLOCK" }, { 5, "IRQ_POLL" }, { 6, "TASKLET" }, { 7, "SCHED" }, { 8, "HRTIMER" }, { 9, "RCU" })
name: softirq_exit
ID: 148
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:unsigned int vec; offset:8;       size:4; signed:0;

print fmt: "vec=%u [action=%s]", REC->vec, __print_symbolic(REC->vec, { 0, "HI" }, { 1, "TIMER" }, { 2, "NET_TX" }, { 3, "NET_RX" }, { 4, "BLOCK" }, { 5, "IRQ_POLL" }, { 6, "TASKLET" }, { 7, "SCHED" }, { 8, "HRTIMER" }, { 9, "RCU" })
name: softirq_raise
ID: 147
format:
        field:unsigned short common_type;       offset:0;       size:2; signed:0;
        field:unsigned char common_flags;       offset:2;       size:1; signed:0;
        field:unsigned char common_preempt_count;       offset:3;       size:1; signed:0;
        field:int common_pid;   offset:4;       size:4; signed:1;

        field:unsigned int vec; offset:8;       size:4; signed:0;

print fmt: "vec=%u [action=%s]", REC->vec, __print_symbolic(REC->vec, { 0, "HI" }, { 1, "TIMER" }, { 2, "NET_TX" }, { 3, "NET_RX" }, { 4, "BLOCK" }, { 5, "IRQ_POLL" }, { 6, "TASKLET" }, { 7, "SCHED" }, { 8, "HRTIMER" }, { 9, "RCU" })
root@lanhao-VirtualBox:/home/lanhao#
