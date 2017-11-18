from divtab import ratio2divisor
print '```csv("Driver ratio request mapping")\n$Ratio_{req}$,$F_{req}$,$Divisor$,$F_{actual}$,$F_{CVF}$'
for ratio_req in range(4, 19):
    (divisor, result_ratio) = ratio2divisor(ratio_req)
    # To avoid another divide, approximate result frequency
    # in 25MHz-ratio steps
    cvf_freq = 25 * result_ratio
    print "%d,%d,%d,%d,%d"%(ratio_req, ratio_req*25, divisor, 1600/divisor, cvf_freq)
print "```"