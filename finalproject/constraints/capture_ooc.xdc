# Standalone core timing, not a board pinout. Control/read ports are clk synchronous.
create_clock -name sys_clk -period 10.000 [get_ports clk]
# Only the asynchronous probe path into stage ONE is cut. Stage two remains timed.
set_false_path -from [get_ports probe_async] -to [get_pins -hier -filter {NAME =~ *probe_meta_reg/D}]
