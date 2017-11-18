valid_ratios = [8, 10, 12, 16] # defined by divider design

def ratio2divisor(ratio_req):
    # Input: 25MHz-based ratio
    # Output: (selected divisor, selected ratio)
    ratio_in = 1600 / 25 # Divider input frequency, in 25Mhz units (a constant)
    # Select valid ratio that is equal or higher than requested
    for r in valid_ratios:
        if r >= ratio_req:
            break
    divisor = ratio_in / r # integer division
    return (divisor, r)