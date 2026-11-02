# PI4IOE5V6408 I2C address
PI4IOE5V6408_ADDR = 0x43 

# Define register addresses using the 'const' function for clarity and to avoid magic numbers
DEVICE_ID_AND_CONTROL = const(0x01)
I_O_DIRECTION = const(0x03)
OUTPUT_PORT = const(0x05)
OUTPUT_HIGH_IMPEDANCE = const(0x07)
INPUT_DEFAULT_STATE = const(0x09)
PULL_UP_DOWN_ENABLE = const(0x0B)
PULL_UP_DOWN_SELECT = const(0x0D)
INPUT_STATUS = const(0x0F)
INTERRUPT_MASK = const(0x11)
INTERRUPT_STATUS = const(0x13)

class PI4IOE5V6408:
    def __init__(self, i2c):
        # Initialize the I2C device and set up the I/O direction and output state
        self.i2c = i2c
        # Set all pins as outputs
        self.i2c.writeto_mem(PI4IOE5V6408_ADDR, I_O_DIRECTION, b'\xff')
        # Set all pins to output low by default (high impedance state)
        self.i2c.writeto_mem(PI4IOE5V6408_ADDR, OUTPUT_HIGH_IMPEDANCE, b'\x00')
    
    def write_pin(self, pin_number, value):        
        # Read the current state of the output port
        rxdata = self.i2c.readfrom_mem(PI4IOE5V6408_ADDR, OUTPUT_PORT, 1)
        # Set the pin state based on the 'value' parameter
        if value:
            # Set the pin high
            new_state = rxdata[0] | (1 << pin_number)
        else:
            # Set the pin low
            new_state = rxdata[0] & ~(1 << pin_number)
        
        # Write the new state back to the output port
        self.i2c.writeto_mem(PI4IOE5V6408_ADDR, OUTPUT_PORT, new_state.to_bytes(1, 'big'))
        
        # Optionally read back the output state to verify the change
        rxdata = self.i2c.readfrom_mem(PI4IOE5V6408_ADDR, OUTPUT_PORT, 1)


