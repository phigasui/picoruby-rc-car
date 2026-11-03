# ==================================================
#  ラジコンカー  (PicoRuby 4.x / Raspberry Pi Pico 2 W)
#  スマホ や パソコン から BLE で うごかすよ
# ==================================================

# ---------- ここは かえて いいよ！ ----------

# スマホに でてくる くるまの なまえ (えいご と すうじ で かいてね)
NAME = "KURUMA-1"

# いちばん はやい スピード (0 から 100 まで)
MAX_SPEED = 100

# 「おどる」ボタンの うごき
#   [ ひだりの タイヤ, みぎの タイヤ, なんびょう ]
#   タイヤは -100 (うしろ) 〜 100 (まえ)
DANCE = [
  [ 100,  100, 0.5],  # まえに すすむ
  [-100, -100, 0.5],  # うしろに さがる
  [ 100, -100, 0.8],  # くるっと まわる
  [-100,  100, 0.8],  # はんたいに まわる
  [   0,    0, 0.3],  # ちょっと とまる
  [ 100,  100, 0.3],  # まえに ジャンプ！
]

# ---------- ここから したは おとなと いっしょに ----------

# モーターが ぎゃくに まわる ときは true に する
INVERT_L = false
INVERT_R = false

# DRV8833 に つないだ ピン (GP ばんごう)
# DRV8833 を 左右に 1 枚ずつ つかい、まえと うしろの モーターを おなじ ピンで うごかす (4WD)
PIN_L = [16, 17]   # ひだりの DRV8833 の AIN1+BIN1, AIN2+BIN2
PIN_R = [18, 19]   # みぎの DRV8833 の AIN1+BIN1, AIN2+BIN2

PWM_FREQ   = 10_000 # Hz。左右の 2 本は同じ PWM スライスなので周波数をそろえる
MIN_DUTY   = 30     # これより弱いと動き出さない。実物で 20〜40 の間で合わせる
# FA-130 は 3V 用のモーター。単3×3 本 (4.5V) で 100% にすると熱くなるので、上限をここで決める
# 75 で約 3.4V。単3 の NiMH (3.6V) なら 90 くらいまで上げてよい
MAX_DUTY   = 75
TICK_MS    = 20     # BLE::UART#start のブロックが呼ばれる間隔
TIMEOUT_MS = 500    # これだけコマンドが来なければ止まる (フェイルセーフ)

begin
  require 'pwm'
rescue Exception
  # 4.x では最初から読み込まれている場合がある
end
require 'ble'

# DRV8833 の 1 チャンネル (IN1/IN2 の 2 本)
class Motor
  def initialize(pin_a, pin_b, invert)
    @a = PWM.new(pin_a, frequency: PWM_FREQ, duty: 0)
    @b = PWM.new(pin_b, frequency: PWM_FREQ, duty: 0)
    @invert = invert
  end

  # value: -100..100 (MAX_SPEED を掛けたあとの値)
  def speed=(value)
    value = -value if @invert
    value = 100 if value > 100
    value = -100 if value < -100
    duty = value.abs
    duty = MIN_DUTY + (MAX_DUTY - MIN_DUTY) * duty / 100 if duty > 0
    if value > 0
      @a.duty(duty)
      @b.duty(0)
    elsif value < 0
      @a.duty(0)
      @b.duty(duty)
    else
      @a.duty(0)
      @b.duty(0)
    end
  end
end

class Car
  def initialize
    @left  = Motor.new(PIN_L[0], PIN_L[1], INVERT_L)
    @right = Motor.new(PIN_R[0], PIN_R[1], INVERT_R)
    @dance_step = nil
    @dance_ticks = 0
  end

  # left, right: -100..100
  def drive(left, right)
    @dance_step = nil
    move(left, right)
  end

  def stop
    @dance_step = nil
    move(0, 0)
  end

  def dancing?
    !@dance_step.nil?
  end

  # BLE を止めないように、ダンスは 1 tick ずつ進める
  def dance
    @dance_step = -1
    @dance_ticks = 0
  end

  def tick
    return unless @dance_step
    if @dance_ticks > 0
      @dance_ticks -= 1
      return
    end
    @dance_step += 1
    step = DANCE[@dance_step]
    if step
      move(step[0], step[1])
      @dance_ticks = (step[2] * 1000 / TICK_MS).to_i
    else
      stop
    end
  end

  private

  def move(left, right)
    @left.speed  = left * MAX_SPEED / 100
    @right.speed = right * MAX_SPEED / 100
  end
end

car = Car.new
uart = BLE::UART.new(name: NAME)

# CYW43 は BLE の初期化で起動するので、LED はそのあとで作る
led = nil
begin
  led = CYW43::GPIO.new(CYW43::GPIO::LED_PIN)
rescue Exception
  led = nil
end

idle_ticks = 0
blink = 0

uart.on_disconnect { car.stop }

uart.start do
  # 通信のやくそく (1 行ずつ):
  #   "D 左 右"  左右の速さ -100..100 で走る
  #   "S"        止まる
  #   "X"        おどる
  while (line = uart.gets_nonblock)
    args = line.strip.split(" ")
    case args[0]
    when "D"
      car.drive(args[1].to_i, args[2].to_i)
    when "S"
      car.stop
    when "X"
      car.dance
    end
    idle_ticks = 0
  end

  car.tick
  idle_ticks += 1
  # おどっている間は止めない。走っている途中で通信が途切れたら止める
  if idle_ticks * TICK_MS > TIMEOUT_MS && !car.dancing?
    car.stop
    idle_ticks = 0
  end

  if led
    if uart.connected?
      led.write(1)
    else
      blink = (blink + 1) % 50
      led.write(blink < 25 ? 1 : 0)
    end
  end
end
