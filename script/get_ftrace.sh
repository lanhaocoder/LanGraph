#!/bin/bash

VERSION=0.1
capture_time=60
output="langraph.dat"
buffer_size=65536
stacktrace=1
tgid=1
gzip=1
events="sched|irq"
clock="perf"
interval=1000000
useperf=0
tracefs_path=`mount|grep tracefs|head -n 1|awk '{print $3}'`

def_ftrace_opt="annotate           1
    bin                0
    blk_cgname         0
    blk_cgroup         0
    blk_classic        0
    block              0
    context-info       1
    disable_on_free    0
    display-graph      0
    event-fork         0
    funcgraph-abstime  0
    funcgraph-cpu      1
    funcgraph-duration 1
    funcgraph-irqs     1
    funcgraph-overhead 1
    funcgraph-overrun  0
    funcgraph-proc     0
    funcgraph-tail     0
    func-no-repeats    0
    func_stack_trace   0
    function-fork      0
    function-trace     1
    graph-time         1
    hash-ptr           1
    hex                0
    irq-info           1
    latency-format     0
    markers            1
    overwrite          1
    pause-on-trace     0
    printk-msg-only    0
    print-parent       1
    raw                0
    record-cmd         1
    record-tgid        0
    sleep-time         1
    stacktrace         0
    sym-addr           0
    sym-offset         0
    sym-userobj        0
    test_nop_accept    0
    test_nop_refuse    0
    trace_printk       1
    userstacktrace     0
    verbose            0"

def_ftrace="buffer_size_kb      65536
    current_tracer      nop
    saved_cmdlines_size 128 
    trace_clock         perf
    tracing_on          0
    trace"

init_ftrace()
{
    currunt_path=`pwd`
    cd $tracefs_path/options
    echo "$def_ftrace_opt" | while read -r line;
    do
    echo $line | awk '{
    if (system("test  -f "$1" ") == 0)
        system("echo "$2" > "$1);
    else
        print "'$tracefs_path'""/options/"$1" not exit"
    }';
    done

    cd $tracefs_path
    echo "$def_ftrace" | while read -r line;
    do
    echo $line | awk '{
    if (system("test  -f "$1" ") == 0)
        system("echo "$2" > "$1);
    else
        print "'$tracefs_path'""/options/"$1" not exit"
    }';
    done
    if [ -f /proc/sys/kernel/ftrace_enabled ]
    then
        echo 1 > /proc/sys/kernel/ftrace_enabled
    fi
    if [ -f /proc/sys/kernel/kptr_restrict ]
    then
        echo 1 > /proc/sys/kernel/kptr_restrict
    fi
    cd $currunt_path
}

init_optione()
{
    echo $buffer_size > $tracefs_path/buffer_size_kb
    echo $clock > $tracefs_path/trace_clock
    if [ $tgid -eq 0 ]
    then
        echo 0 > $tracefs_path/options/record-tgid
    else
        echo 1 > $tracefs_path/options/record-tgid
    fi
    if [ $stacktrace -eq 0 ]
    then
        echo 0 > $tracefs_path/options/sym-addr
        echo 0 > $tracefs_path/options/sym-offset
        echo 0 > $tracefs_path/options/sym-userobj
        echo 0 > $tracefs_path/options/userstacktrace
        echo 0 > $tracefs_path/options/stacktrace
    else
        echo 1 > $tracefs_path/options/sym-addr
        echo 1 > $tracefs_path/options/sym-offset
        echo 1 > $tracefs_path/options/sym-userobj
        echo 1 > $tracefs_path/options/userstacktrace
        echo 1 > $tracefs_path/options/stacktrace
    fi
    currunt_path=`pwd`
    cd $tracefs_path/events/
    echo $events | awk -F"|" '{
        for(i=1;i<=NF;i++)
        {
            if (system("test  -f "$1"/enable") == 0)
                system("echo 1 > "$i"/enable");
            else
                print $i " not exist"
        }
    }';
    cd $currunt_path
    echo 0 > $tracefs_path/tracing_on
    echo > $tracefs_path/trace
}

is_cmd_exist()
{
    local cmd="$1"

    which "$cmd" >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        return 0
    fi

    return 2
}

start_perf()
{
    is_cmd_exist perf
    if [ $? -ne 0 ]
    then
        echo "not exist perf, not get perf"
        return 0
    fi
    if [[ "`uname -a`" =~ "86" ]]
    then
        call_graph="dwarf"
    else
        call_graph="fs"
    fi

    perf record -D -1 -a               \
                -g --call-graph=$call_graph -F 1000 \
                -- sleep `expr $capture_time + 5` &
}

save_perf()
{
    is_cmd_exist perf
    if [ $? -ne 0 ]
    then
        echo "not exist perf, not get perf"
        return 0
    fi
    if [[ "`uname -a`" =~ "86" ]]
    then
        call_graph="dwarf"
    else
        call_graph="fs"
    fi

    perf script -F comm,pid,tid,cpu,flags,time,event,ip,sym,dso,trace,symoff,dso,ipc > $output.perf.log
}
start_capture()
{
    if [ $useperf -eq 1 ]
    then
        start_perf
    fi
    echo 1 > $tracefs_path/tracing_on
    echo "Capture for "$capture_time" seconds start."
    echo "Enter Ctrl+C to stop capture..."
    sleep $capture_time
}

get_user_symbol()
{
    is_cmd_exist addr2line
    if [ $? -ne 0 ]
    then
        echo "not exist addr2line, not get user symbol"
        return 0
    fi
    echo "Get user symbol start..."
    result=`grep "^ => " $output |sort|uniq`
    echo "$result" |sed 's/\[/ /'|sed 's/+/ /'|sed 's/\]/ /'|while read -r line;
    do
    echo $line | awk '{
    if ($3 !~ "/")
        if ($2 !~ ">")
            if (system("test  -f "$2" ") == 0) {
                system("echo -n \"# user_symbol: "$2" "$3" \" >> ""'$output'");
                system("addr2line -p -f -e "$2" -a "$3" >> ""'$output'");
            }
    }';
    done
}

save_result()
{
    echo "Saving results, please wait"
    echo 0 > $tracefs_path/tracing_on
    cp $tracefs_path/trace $output

    get_user_symbol

    if [ $useperf -eq 1 ]
    then
        save_perf
    fi

    if [ $gzip -eq 1 ]
    then
        gzip -f $output
    fi
}
help_handle()
{
    cat << EOF
usage : -t <time in second> capture time default=60
        -o <output> output path default=langraph.dat
        -m <size_kb> ftrace buffer size per cpu in kb default=65536
        -s <enable> enable stacktrace default=1
        -t <enable> format with tgid default=1
        -z <enable> output will gzip default=1
        -e <events> trace events default=sched|irq
           available events in $tracefs_path/available_events
           if use more than one event, use '|' as a separator
           if use subevent use '/' as a separator
           for example: sched/sched_wakeup|sched/sched_waking|irq
           means sched/sched_wakeup and sched/sched_waking and irq
        -c <clock> clock source default=perf
           available type in $tracefs_path/trace_clock
           local global counter uptime perf
        -p <enable> use perf in the same time default=0
        -i <time in second> save buffer interval default=1000000
        -h help
        -v version
EOF
        exit 0
}

while getopts "t:o:m:s:T:z:e:c:i:p:hv" opt
do
    case $opt in
        t)
            capture_time=$OPTARG
            ;;
        o)
            output=$OPTARG
            ;;
        m)
            buffer_size=$OPTARG
            ;;
        s)
            stacktrace=$OPTARG
            ;;
        T)
            tgid=$OPTARG
            ;;
        z)
            gzip=$OPTARG
            ;;
        e)
            events=$OPTARG
            ;;
        c)
            clock=$OPTARG
            ;;
        p)
            useperf=$OPTARG
            ;;
        i)
            interval=$OPTARG
            ;;
        h)
            help_handle
            ;;
        v)
            echo "$0 version is $VERSION"
            ;;
        ?)
        echo "unkown"
        help_handle
        exit 1;;
esac done

trap "save_result" 2
trap "save_result" 5
trap "save_result" 9

init_ftrace
init_optione
start_capture
save_result
