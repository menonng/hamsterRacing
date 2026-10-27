const int pinX = A1; //A1과 VRy 연결
const int pinY = A0;

const int centerX = 505;
const int centerY = 497;
const int deadzone = 10;

const int scale = 80;

SoftwareSerial BTSerial(2,3);

void setup() {
  BTSerial.begin(9600);
}

void loop() {
  int valX = analogRead(pinX);
  int valY = analogRead(pinY);

  BTSerial.print(valX);
  BTserial.println(valY);

  int dx = valX - centerX;
  int dy = valY - centerY;

  if (abs(dx) <= deadzone) dx = 0;
  if (abs(dy) <= deadzone) dy = 0;

  float u = (dx)/512.0f;
  float v = (dy)/512.0f;

  float l = v+max(u,0.0f);
  float r = v+max(-u,0.0f);

  float m = max(1.0f,max(abs(l),abs(r)));

  int left = (int)(l/m*scale);
  int right = (int)(r/m*scale);


  BTSerial.print(left);
  BTSerial.print(" | ");
  BTSerial.println(right);

  delay(1000);
}