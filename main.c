#include <trace-cmd.h>

static int print_events(struct tracecmd_input *handle, struct tep_record *record,
		       int cpu, void *data)
{
	struct tep_handle *tep = tracecmd_get_tep(handle);
	struct trace_seq *seq = data;

	trace_seq_reset(seq);
	tep_print_event(tep, seq, record, "%6.1000d", TEP_PRINT_TIME);
	trace_seq_printf(seq, " [%03d] ", cpu);
	tep_print_event(tep, seq, record, "%s-%d %s %s\n",
			TEP_PRINT_COMM, TEP_PRINT_PID,
			TEP_PRINT_NAME, TEP_PRINT_INFO);
	trace_seq_do_printf(seq);
	return 0;
}

int main()
{
	struct trace_seq seq;
	struct tracecmd_input *handle;
	int ret;

	trace_seq_init(&seq);
	handle = tracecmd_open_head("trace.dat", 0);
	if (handle == NULL) {
		printf("cannot open trace.dat");
		return -1;
	}
	ret = tracecmd_iterate_events(handle, NULL, 0, print_events, &seq);

	tracecmd_close(handle);
	trace_seq_destroy(&seq);

	return 0;
}

