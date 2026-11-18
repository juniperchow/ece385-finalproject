`timescale 1ns/1ps
`default_nettype none
module tb_capture_core;
    parameter integer SAMPLE_DIV = 1000;
    logic clk;
    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end
    logic rst, probe_async, arm, abort_capture;
    logic [1:0] trigger_mode;
    logic busy, armed, done, done_pulse;
    logic [10:0] sample_count;
    logic rd_en;
    logic [9:0] rd_addr;
    logic rd_valid;
    logic [15:0] rd_data;
    capture_core #(.SAMPLE_DIV(SAMPLE_DIV)) dut (.*);
    string vectors;
    integer fd, fields, reps, ctrl, address, flags, count, data;
    integer cycles;
    logic [4:0] actual_flags;
    assign actual_flags = {rd_valid, done_pulse, done, armed, busy};

    initial begin
        rst = 1'b1; probe_async = 1'b0; arm = 1'b0; abort_capture = 1'b0;
        trigger_mode = '0; rd_en = 1'b0; rd_addr = '0; cycles = 0;
        if (!$value$plusargs("vectors=%s", vectors)) $fatal(1, "Missing +vectors=path");
        fd = $fopen(vectors, "r");
        if (fd == 0) $fatal(1, "Cannot open %s", vectors);
        while (!$feof(fd)) begin
            fields = $fscanf(fd, "%h %h %h %h %h %h\n", reps, ctrl, address, flags, count, data);
            if (fields != 6 || reps < 1) $fatal(1, "Malformed vector after cycle %0d", cycles);
            repeat (reps) begin
                @(negedge clk);
                // Probe changes off the rising edge; synchronizer latency is checked by the oracle.
                rst = ctrl[0]; arm = ctrl[1]; abort_capture = ctrl[2];
                probe_async = ctrl[3]; trigger_mode = ctrl[5:4]; rd_en = ctrl[6];
                rd_addr = address[9:0];
                @(posedge clk);
                #1;
                cycles = cycles + 1;
                if (actual_flags !== flags[4:0] || sample_count !== count[10:0])
                    $fatal(1, "cycle=%0d ctrl=%h flags got=%h want=%h count got=%0d want=%0d",
                           cycles, ctrl, actual_flags, flags[4:0], sample_count, count);
                if (flags[5] && rd_data !== data[15:0])
                    $fatal(1, "cycle=%0d address=%0d data got=%h want=%h",
                           cycles, address, rd_data, data[15:0]);
            end
        end
        $fclose(fd);
        if (cycles == 0) $fatal(1, "Empty test");
        $display("PASS capture_core divisor=%0d cycles=%0d", SAMPLE_DIV, cycles);
        $finish;
    end
    initial begin
        #200000000;
        $fatal(1, "Watchdog expired");
    end
endmodule
`default_nettype wire
