# vivado -mode batch -source scripts/synth_capture.tcl
# Can be invoked from any directory; no dependency on the starter XPR or HDMI IP.
set root [file normalize [file join [file dirname [info script]] ..]]
set out [file join $root build capture vivado]
file mkdir $out
create_project -in_memory -part xc7s50csga324-1
read_verilog -sv [file join $root rtl capture_core.sv]
read_xdc [file join $root constraints capture_ooc.xdc]
synth_design -top capture_core -part xc7s50csga324-1 -mode out_of_context
set brams [get_cells -hier -filter {REF_NAME =~ RAMB*}]
if {[llength $brams] == 0} { error "Capture memory did not infer block RAM" }
set meta_d [get_pins -hier -filter {NAME =~ *probe_meta_reg/D}]
if {[llength $meta_d] != 1} { error "Probe synchronizer first-stage constraint did not match" }
report_utilization -file [file join $out utilization.rpt]
report_timing_summary -file [file join $out timing.rpt]
report_cdc -file [file join $out cdc.rpt]
write_checkpoint -force [file join $out capture_core.dcp]
puts "Capture synthesis complete; BRAM cells: [llength $brams]; reports: $out"
