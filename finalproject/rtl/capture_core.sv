`default_nettype none
// Explicit input net kinds are required by Vivado 2022.2 with default_nettype none.
// Single-channel, post-trigger acquisition. All ports except probe_async are clk synchronous.
module capture_core #(
    parameter integer SAMPLE_DIV = 1000
) (
    input  wire logic         clk,
    input  wire logic         rst,
    input  wire logic         probe_async,
    input  wire logic         arm,
    input  wire logic         abort_capture,
    input  wire logic  [1:0]  trigger_mode, // 0 immediate, 1 rising, 2 falling, 3 either
    output      logic         busy,
    output      logic         armed,
    output      logic         done,
    output      logic         done_pulse,
    output      logic  [10:0] sample_count,
    input  wire logic         rd_en,
    input  wire logic  [9:0]  rd_addr,
    output      logic         rd_valid,
    output      logic  [15:0] rd_data
);
    localparam integer DIV_W = (SAMPLE_DIV > 1) ? $clog2(SAMPLE_DIV) : 1;
    // Illegal configurations fail elaboration without simulation-only RTL assertions.
    generate if (SAMPLE_DIV < 4) begin : g_invalid_div
        SAMPLE_DIV_must_be_at_least_four invalid_configuration();
    end endgenerate

    (* ASYNC_REG = "TRUE", SHREG_EXTRACT = "NO" *) logic probe_meta, probe_sync;
    logic [2:0] warmup;
    logic [DIV_W-1:0] divider;
    logic sample_ce, previous_sample, previous_valid;
    logic [1:0] mode_latched;
    typedef enum logic [1:0] {IDLE, WAIT_TRIGGER, CAPTURE, COMPLETE} state_t;
    state_t state;
    logic trigger_hit, accept_arm, write_sample, read_sample;
    logic [9:0] wr_addr;
    (* ram_style = "block" *) logic [15:0] samples [0:1023];

    always_ff @(posedge clk) begin
        if (rst) begin
            probe_meta <= 1'b0;
            probe_sync <= 1'b0;
            warmup <= 3'b000;
        end else begin
            probe_meta <= probe_async;
            probe_sync <= probe_meta;
            warmup <= {warmup[1:0], 1'b1};
        end
    end

    assign sample_ce = (divider == DIV_W'(SAMPLE_DIV - 1)) && warmup[2];
    always_ff @(posedge clk) begin
        if (rst) begin
            divider <= '0;
            previous_sample <= 1'b0;
            previous_valid <= 1'b0;
        end else begin
            if (divider == DIV_W'(SAMPLE_DIV - 1)) divider <= '0;
            else divider <= divider + 1'b1;
            if (sample_ce) begin
                previous_sample <= probe_sync;
                previous_valid <= 1'b1;
            end
        end
    end

    always_comb begin
        case (mode_latched)
            2'd0: trigger_hit = 1'b1;
            2'd1: trigger_hit = previous_valid && !previous_sample && probe_sync;
            2'd2: trigger_hit = previous_valid && previous_sample && !probe_sync;
            2'd3: trigger_hit = previous_valid && (previous_sample != probe_sync);
            default: trigger_hit = 1'b0;
        endcase
    end
    assign busy = (state == WAIT_TRIGGER) || (state == CAPTURE);
    assign armed = (state == WAIT_TRIGGER);
    assign done = (state == COMPLETE);
    assign accept_arm = arm && !busy;
    assign write_sample = !rst && !abort_capture && sample_ce &&
                          ((state == CAPTURE) || ((state == WAIT_TRIGGER) && trigger_hit));
    assign read_sample = !rst && !abort_capture && !accept_arm && done && rd_en;

    // No reset on the memory or its output register: infer synchronous simple-dual-port BRAM.
    // Ownership gating prevents simultaneous reads and writes, including re-arm collisions.
    always_ff @(posedge clk) begin
        if (write_sample) samples[wr_addr] <= {15'b0, probe_sync};
        if (read_sample) rd_data <= samples[rd_addr];
    end
    always_ff @(posedge clk) begin
        if (rst) rd_valid <= 1'b0;
        else rd_valid <= read_sample;
    end

    always_ff @(posedge clk) begin
        if (rst || abort_capture) begin
            state <= IDLE;
            wr_addr <= '0;
            sample_count <= '0;
            mode_latched <= 2'd0;
            done_pulse <= 1'b0;
        end else begin
            done_pulse <= 1'b0;
            if (accept_arm) begin
                state <= WAIT_TRIGGER;
                wr_addr <= '0;
                sample_count <= '0;
                mode_latched <= trigger_mode;
            end else if (write_sample) begin
                sample_count <= sample_count + 1'b1;
                if (wr_addr == 10'd1023) begin
                    state <= COMPLETE;
                    done_pulse <= 1'b1;
                end else begin
                    wr_addr <= wr_addr + 1'b1;
                    state <= CAPTURE;
                end
            end
        end
    end
endmodule
`default_nettype wire
