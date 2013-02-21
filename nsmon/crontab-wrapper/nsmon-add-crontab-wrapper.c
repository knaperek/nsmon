#include <stdio.h>
#include <sys/types.h>
#include <unistd.h>

#define BINNARY "/sbin/nsmon-add-crontab"

int main(int argc, char** argv) {

		if (argc != 2) {
				fprintf(stderr, "Wrong number of arguments\n");
				return 1;
		}

		setuid(0);
		setgid(0);
		// printf("wrapper starting\n");
		execl(BINNARY, BINNARY, argv[1], (char *) 0);

		return 0;
}

