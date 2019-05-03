import numpy as np
from integrators import rk4_general


class HysteresisRod:
    # TODO: is the limiting cycle B on the y-axis or is it M = B - u0*H?

    def __init__(self, br, bs, hc, volume=1, mass=1, axes_alignment=np.array([1, 0, 0]), h_initial=0, b_initial=0,
                 integration_size=None, scale_factor=10**-5):
        self.u0 = 4 * np.pi * 10**-7
        self.scale_factor = scale_factor
        self.br = br
        self.bs = bs
        self.hc = hc
        self.k = (1/hc) * np.tan(np.pi * br / 2 / bs)
        self.volume = volume
        self.mass = mass
        self.density = mass/volume
        self.axes_alignment = axes_alignment
        self.b_previous = b_initial
        self.h_previous = h_initial
        self.h_current = h_initial
        self.b_current = b_initial
        if integration_size is not None:
            self.b = np.zeros(integration_size)
            self.h = np.zeros(integration_size)
        else:
            self.b = self.h = None

    def b_field_top(self, h):
        return 2 * self.bs * np.arctan(self.k * (h + self.hc))/np.pi

    def b_field_bottom(self, h):
        return 2 * self.bs * np.arctan(self.k * (h - self.hc))/np.pi

    def b_field_top_derivative(self, h):
        return 2 * self.bs * self.k / (1 + (h + self.hc)**2 * self.k**2) / np.pi

    def b_field_bottom_derivative(self, h):
        return 2 * self.bs * self.k / (1 + (h - self.hc)**2 * self.k**2) / np.pi

    def mag_process_positive_h(self, h, b):
        return self.u0 + (self.b_field_top(h) - b) * (self.b_field_bottom_derivative(h) - self.u0) / \
               (self.b_field_top(h) - self.b_field_bottom(h))

    def mag_process_negative_h(self, h, b):
        return self.u0 + (b - self.b_field_bottom(h)) * (self.b_field_top_derivative(h) - self.u0) / \
               (self.b_field_top(h) - self.b_field_bottom(h))

    def propagate_magnetization(self, h):
        self.h_current, self.h_previous = h, self.h_current
        self.b_previous = self.b_current
        step = self.h_current - self.h_previous
        if self.h_current >= self.h_previous:
            self.b_current = rk4_general(self.mag_process_positive_h, step, self.h_current, self.b_previous)
            # This is the rk4 version of simple euler method:
            # self.b_current = self.b_previous + self.mag_process_positive_h(self.h_current, self.b_previous) * step
        else:
            self.b_current = rk4_general(self.mag_process_negative_h, step, self.h_current, self.b_previous)

    def propagate_and_save_magnetization(self, h, i):
        self.h[i+1] = h
        step = self.h[i+1] - self.h[i]
        if self.h[i+1] >= self.h[i]:
            # self.b[i+1] = rk4_general(self.mag_process_positive_h, step, self.h[i+1], self.b[i])
            self.b[i+1] = self.b[i] + self.mag_process_positive_h(self.h[i+1], self.b[i]) * step
        else:
            # self.b[i+1] = rk4_general(self.mag_process_negative_h, step, self.h[i+1], self.b[i])
            self.b[i+1] = self.b[i] + self.mag_process_negative_h(self.h[i+1], self.b[i]) * step
        self.h_current = h
        self.b_current = self.b[i+1]

    def plot_limiting_cycle(self, hmin, hmax):
        import matplotlib.pyplot as plt
        plt.figure()
        h = np.linspace(hmin, hmax, 1000)
        top = self.b_field_top(h)
        bottom = self.b_field_bottom(h)
        plt.plot(h, top, 'C0')
        plt.plot(h, bottom, 'C0')
        plt.axvline(x=0, color='k')
        plt.axhline(y=0, color='k')
        plt.axvline(x=self.hc, color='r', ls='dashed', alpha=0.3)
        plt.axvline(x=-self.hc, color='r', ls='dashed', alpha=0.3)
        plt.axhline(y=self.br, color='r', ls='dashed', alpha=0.3)
        plt.axhline(y=-self.br, color='r', ls='dashed', alpha=0.3)
        plt.axhline(y=self.bs, color='r', ls='dashed', alpha=0.3)
        plt.axhline(y=-self.bs, color='r', ls='dashed', alpha=0.3)
        plt.title('Limiting Hysteresis Cycle')
        plt.xlabel('H')
        plt.ylabel('B')

    def plot_limiting_cycle_derivative(self, hmin, hmax):
        import matplotlib.pyplot as plt
        plt.figure()
        h = np.linspace(hmin, hmax, 1000)
        top = self.b_field_top_derivative(h)
        bottom = self.b_field_bottom_derivative(h)
        plt.plot(h, top)
        plt.plot(h, bottom)
        plt.axvline(x=0, color='k')
        plt.title('Limiting Hysteresis Cycle Derivative')
        plt.xlabel('H')
        plt.ylabel('B')


if __name__ == "__main__":
    import matplotlib.pyplot as plt


    # h = np.linspace(0, 600, 1000)
    time = np.linspace(0, 10, 1000)
    h = 300 * np.sin(time)
    # h = np.concatenate([np.arange(0, 600, 0.5), np.arange(600, -600, -0.5), np.arange(-600, 0, 0.5)])
    b = np.zeros_like(h)

    hyst_rod = HysteresisRod(8, 10, 100, integration_size=1000)
    # hyst_rod.plot_limiting_cycle(-600, 600)
    hyst_rod.plot_limiting_cycle_derivative(-100, 100)

    # for i, da in enumerate(h[:-1]):
    #     step = h[i + 1] - h[i]
    #     if h[i+1] >= h[i]:
    #         # b[i + 1] = b[i] + hyst_rod.mag_process_positive_h(h[i+1], b[i]) * step
    #         b[i+1] = rk4_general(hyst_rod.mag_process_positive_h, step, h[i+1], b[i])
    #     else:
    #         # b[i + 1] = b[i] + hyst_rod.mag_process_negative_h(h[i + 1], b[i]) * step
    #         b[i+1] = rk4_general(hyst_rod.mag_process_negative_h, step, h[i+1], b[i])

    # h = np.zeros(1000)
    # dir = 1
    # for i in range(len(h[:-1])):
    #     rand = np.random.random()
    #     if rand < 0.97:
    #         h[i+1] = h[i] + dir*5
    #     else:
    #         h[i+1] = h[i] - dir*5
    #         dir = -1*dir
    #
    # for i, da in enumerate(h[:-1]):
    #     hyst_rod.propagate_magnetization(h[i+1])
    #     b[i+1] = hyst_rod.b_current

    for i, da in enumerate(h[:-1]):
        hyst_rod.propagate_and_save_magnetization(h[i+1], i)

    # plt.figure()
    hyst_rod.plot_limiting_cycle(-600, 600)
    plt.plot(hyst_rod.h, hyst_rod.b, color='red', linestyle='--')
    plt.show()
