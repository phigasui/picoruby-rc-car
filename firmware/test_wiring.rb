# 配線チェック (タイヤを浮かせてから実行する)
# 左右のモーターを 1 つずつ、前・後ろの順に 1 秒ずつ回す
# 4WD では左右それぞれ前輪と後輪が一緒に回る。片方だけ逆に回るときは、そのモーターの 2 本を入れ替える

begin
  require 'pwm'
rescue Exception
end

FREQ = 10_000
DUTY = 60

pins = {
  "ひだり まえ   (GP16 / AIN1+BIN1)" => 16,
  "ひだり うしろ (GP17 / AIN2+BIN2)" => 17,
  "みぎ   まえ   (GP18 / AIN1+BIN1)" => 18,
  "みぎ   うしろ (GP19 / AIN2+BIN2)" => 19,
}

pwms = {}
pins.each { |label, pin| pwms[pin] = PWM.new(pin, frequency: FREQ, duty: 0) }

pins.each do |label, pin|
  puts "#{label} ... 1 びょう"
  pwms[pin].duty(DUTY)
  sleep 1
  pwms[pin].duty(0)
  sleep 1
end

puts "りょうほう まえ ... 1 びょう"
pwms[16].duty(DUTY)
pwms[18].duty(DUTY)
sleep 1
pwms.each_value { |p| p.duty(0) }

puts "おわり"
