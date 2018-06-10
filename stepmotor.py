import wiringpi
import time
import threading
import datetime


class ConfigurationError(Exception):
    """Raise when the user tries to configure the system in a bad way"""


class Stepper:
    def __init__(self, i1, i2, i3, i4, debug=False):
        wiringpi.wiringPiSetup()
        self.inp = [None, None, None, None]
        self.check_pins(i1, i2, i3, i4)
        wiringpi.pinMode(i1, 1)
        wiringpi.pinMode(i2, 1)
        wiringpi.pinMode(i3, 1)
        wiringpi.pinMode(i4, 1)
        wiringpi.digitalWrite(i1, 0)
        wiringpi.digitalWrite(i2, 0)
        wiringpi.digitalWrite(i3, 0)
        wiringpi.digitalWrite(i4, 0)
        self.num_step = 0
        self.half = [[1, 0, 0, 1],  # step 0
                     [1, 0, 0, 0],  # step 1
                     [1, 1, 0, 0],  # step 2
                     [0, 1, 0, 0],  # step 3
                     [0, 1, 1, 0],  # step 4
                     [0, 0, 1, 0],  # step 5
                     [0, 0, 1, 1],  # step 6
                     [0, 0, 0, 1]]  # step 7
        self.actspeed = 0
        self.direction = None
        self.actual_speed = 0

        # Hardware constrains
        self.acceleration_factor = 1
        self.MIN_SPEED = 10    # Steps/sec
        self.MAX_SPEED = 500  # Steps/sec

        # Debugging variables
        self.debug = False
        self.debug_filename = ""
        if debug:
            self.debug = True

            # outputs ['YYYY-MM-DD', 'hh:mm:ss.milliseconds']
            date = str(datetime.datetime.now()).split(" ")
            actual_time = date[1].split(".")
            # extract YYY-MM-DD
            day = date[0]
            # extract hh:mm:ss
            hour = actual_time[0]

            filepath = "debugfiles/" + "debugging_" + day + "_" + hour + ".dat"
            f = open(filepath, "w+")
            f.write("")
            f.close()
            self.debug_filepath = filepath
        self.absolute_time = 0

    def check_pins(self, i1, i2, i3, i4):
        """Control if selected pin numbers are valid"""
        try:
            int(i1)
        except ValueError:
            raise ConfigurationError("The first pin ID is not an integer: {}".format(i1))
        try:
            int(i2)
        except ValueError:
            raise ConfigurationError("The second pin ID is not an integer: {}".format(i2))
        try:
            int(i3)
        except ValueError:
            raise ConfigurationError("The third pin ID is not an integer: {}".format(i3))
        try:
            int(i4)
        except ValueError:
            raise ConfigurationError("The fourth pin ID is not an integer: {}".format(i4))

        input_pins = [int(i1), int(i2), int(i3), int(i4)]

        # wiringpi library supports only 17 GPIO pins. See the official documentation for more informations
        for i in range(len(input_pins)):
            if input_pins[i] not in list(range(0, 17)):
                raise ConfigurationError("The pin number "
                                         "{} does not exist. Valid pin numbers are from 0 to 16.".format(i+1))

        # control if there is not a single pin used two times
        if len(set(input_pins)) != 4:
            raise ConfigurationError("There are two different pins with the same number. Pins must have unique numbers")

        self.inp = input_pins

    def stop(self):
        wiringpi.digitalWrite(self.inp[0], 0)
        wiringpi.digitalWrite(self.inp[2], 0)
        wiringpi.digitalWrite(self.inp[3], 0)
        wiringpi.digitalWrite(self.inp[1], 0)

    def run_one_step(self):
        """Change the power configuration of the pins in order to do one step in a certain direction."""
        phase = (self.num_step % 8) * self.direction

        # Do the step
        for k in range(0, 4):
            wiringpi.digitalWrite(self.inp[k], self.half[phase][k])

    def move(self, step_num, speed):
        """Manages the acceleration, constant movement and deceleration of the stepper.

        *step_num* can be positive and negative: negative values make the engine turn in the opposite direction;
        *speed* must be positive, and should respect the hardware limitations"""

        # Verify parameters' validity
        if step_num is None:
            return "Invalid input. You should choose a value for *step_num*"
        if speed is None:
            return "Invalid input. You should choose a value for *speed*. A possible value could be 250 step/s"

        try:
            step_num = int(step_num)
        except(TypeError, ValueError):
            return "Invalid input. step_num has to be an integer"
        if step_num < 0:
            return "Invalid input. step_num has to be positive"

        try:
            speed = int(speed)
        except(TypeError, ValueError):
            return "Invalid input. speed has to be an integer"

        if speed >= 0:
            self.direction = 1
        if speed < 0:
            self.direction = -1
            speed = abs(speed)

        # Apply hardware's speed limits
        if speed > self.MAX_SPEED:
            speed = self.MAX_SPEED
        if speed < self.MIN_SPEED:
            speed = self.MIN_SPEED

        # Number of steps of the speed changing intervals
        acceleration_steps = int(speed / self.acceleration_factor)

        # Control if the acceleration phases are not too long
        if acceleration_steps > (step_num / 2):
            acceleration_steps = (step_num / 2)
        constant_speed_steps = step_num - (2 * acceleration_steps)
        self._linear_acceleration(acceleration_steps, acc_is_positive=True)

        # Set the right speed when acceleration phase is too short, and the engine couldn't reach the required speed.
        if speed > self.actual_speed:
            speed = self.actual_speed
        self._move_with_constant_speed(constant_speed_steps, speed)
        self._linear_acceleration(acceleration_steps, acc_is_positive=False)

    def _move_with_constant_speed(self, steps, speed):
        """Make the stepper move with a constant speed.
        Do not call this method manually, it could damage your engine."""
        self.actual_speed = speed
        t = 1 / self.actual_speed

        for s in range(int(steps)):
            # Control message. Helps during tests
            # print(self.num_step, self.actual_speed, t)
            self.run_one_step()
            self.num_step += 1 * self.direction
            time.sleep(t)

    def _linear_acceleration(self, steps, acc_is_positive):
        """Make the stepper accelerate/decelerate linearly with the time. Acceleration in controlled trough the
        *self.acceleration_factor* parameter, and its standard value is set to 1.
        Do not call this method manually, it could damage your engine."""
        acc_or_dec = 1
        count = 1
        if acc_is_positive:
            # Engine is accelerating
            # Correct the speed in order to avoid ZeroDivisionError during the first definition of *t*
            self.actual_speed = 1 * self.acceleration_factor

        if not acc_is_positive:
            # Engine is decelerating
            acc_or_dec = -1

        while count <= steps:
            # Set the time between every step (~speed)
            t = 1 / self.actual_speed

            # Control message. Helps during tests
            # print(self.num_step, self.actual_speed, t)
            self.run_one_step()

            # Make the acceleration
            self.actual_speed += 1 * self.acceleration_factor * acc_or_dec
            self.num_step += 1 * self.direction
            time.sleep(t)
            count += 1

        # Set the speed to 0 when the engine ends the deceleration
        if not acc_is_positive:
            self.actual_speed = 0


# motor1 = Stepper(7, 0, 2, 3)
# while 0:
#     motor1.move(2000, int(4096/2), 1)
#     motor1.stop()
#     time.sleep(2)
#     motor1.move(2000, int(4096/2), -1)
#     motor1.stop()
#     time.sleep(2)
