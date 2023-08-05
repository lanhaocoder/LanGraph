#!/bin/bash

VERSION=0.1
capture_time=60
output="langraph"
buffer_size=65536
stacktrace=1
tgid=1
gzip=0
user_symbol=1
events="sched|irq"
clock="perf"
interval=1000000
useperf=0
useftrace=1
ftrace_output_name="ftrace.log"
perf_output_name="perf.log"
freq=100
currunt_path=$(pwd)
if [ -d "/sys/kernel/debug/tracing" ]
then
    tracefs_path="/sys/kernel/debug/tracing"
else
    tracefs_path=`mount|grep debugfs|head -n 1|awk '{print $3}'`/tracing
    if [ -d $tracefs_path ]
    then
        useftrace=0
        echo "cannot found ftrace path, disable ftrace capture"
    fi
fi

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

init_ftrace_optione()
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
            if (system("test -f "$1"/enable") == 0)
                system("echo 1 > "$i"/enable");
            else
                print $i " not exist"
        }
    }';
    cd $currunt_path
    echo 0 > $tracefs_path/tracing_on
    echo > $tracefs_path/trace
}

init_ftrace()
{
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
    init_ftrace_optione
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

save_perf()
{
    is_cmd_exist perf
    if [ $? -ne 0 ]
    then
        echo "not exist perf, not get perf"
        return 0
    fi
    cd $currunt_path
    cd $output
    perf script -F comm,pid,tid,cpu,flags,time,event,ip,sym,dso,trace,symoff,dso,ipc > $perf_output_name
    cd $currunt_path
}

get_user_symbol()
{
    is_cmd_exist addr2line
    if [ $? -ne 0 ]
    then
        echo "not exist addr2line, not get user symbol"
        return 0
    fi
    cd $currunt_path
    echo "Get user symbol start..."
    result=`grep "^ => " $output/$ftrace_output_name |sort|uniq`
    echo "$result" |sed 's/\[/ /'|sed 's/+/ /'|sed 's/\]/ /'|while read -r line;
    do
    echo $line | awk '{
    if ($3 !~ "/")
        if ($2 !~ ">")
            if (system("test  -f "$2" ") == 0) {
                system("echo -n \"# user_symbol: "$2" "$3" \" >> ""'$output'""/""'$ftrace_output_name'");
                system("addr2line -i -p -f -e "$2" -a "$3" >> ""'$output'""/""'$ftrace_output_name'");
            }
    }';
    done
}

save_result()
{
    trap : INT HUP QUIT TERM

    echo "Saving results, please wait"
    echo 0 > $tracefs_path/tracing_on
    cd $currunt_path
    cp $tracefs_path/trace $output/$ftrace_output_name

    if [ $user_symbol -eq 1 ]
    then
        get_user_symbol
    fi

    if [ $useperf -eq 1 ]
    then
        save_perf
    fi

    if [ $useperf -eq 1 ]
    then
        save_perf
    fi

    if [ $gzip -eq 1 ]
    then
        cd `dirname $output`
        tar -zcf `basename $output`.tar.gz `basename $output`
        echo "result is `realpath $output.tar.gz`"
    else
        echo "result is `realpath $output`"
    fi
}

start_perf()
{
    is_cmd_exist perf
    if [ $? -ne 0 ]
    then
        echo "not exist perf, not get perf"
        return 0
    fi
    echo "start perf capture"
    case "`uname -a`" in
        *x86*)
            call_graph="dwarf"
            ;;
        *)
            call_graph="fp"
            ;;
    esac
    cd $currunt_path
    cd $output
    perf record -a -g --call-graph=$call_graph -F $freq -m 128M \
                -- sleep `expr $capture_time + 5` &
    cd $currunt_path
}

start_ftrace()
{
    echo "start ftrace capture"
    init_ftrace
    echo 1 > $tracefs_path/tracing_on
}

start_capture()
{
    if [ $useperf -eq 1 ]
    then
        start_perf
    fi
    if [ $useftrace -eq 1 ]
    then
        start_ftrace
    fi
    echo "Capture for "$capture_time" seconds start."
    echo "Enter Ctrl+C to stop capture..."
    trap "save_result" INT HUP QUIT TERM
    sleep $capture_time
    trap : INT HUP QUIT TERM
}

help_handle()
{
    cat << EOF
usage : -t <time in second> capture time default=60
        -o <output> output directory path default=langraph
        -z <enable> output will gzip default=1
        -e <events> trace events default=sched|irq
           available events in $tracefs_path/available_events
           if use more than one event, use '|' as a separator
           if use subevent use '/' as a separator
           for example: sched/sched_wakeup|sched/sched_waking|irq
           means sched/sched_wakeup and sched/sched_waking and irq
        -p <enable> use perf in the same time default=0
        -y <enable> use ftrace user space symbol default=1
        -h help
        -v version
EOF
        exit 0
}

while getopts "t:o:m:s:T:z:e:c:i:p:y:hv" opt
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
        y)
            user_symbol=$OPTARG
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

if [ -d $output ]
then
    output_full=`realpath $output`
    if [ -n "`mount | grep tmpfs | grep \"$output_full\"`" ]
    then
        echo $output_full had mounted
    else
        mkdir -p $output
        mount -t tmpfs nodev $output
    fi
else
    mkdir -p $output
    mount -t tmpfs nodev $output
fi

start_capture
save_result
