#include <Arduino.h>

#include <eXoCAN.h>
#include "SPI.h"
// #include <AS5048A.h>

#define bluePillLED PC13
#define CS1Pin PB0
#define CS2Pin PB1

#define M1_D PA15
#define M1_P PB3
#define M2_D PB4
#define M2_P PB5

HardwareSerial Serial2(PA_3, PA_2);

// AS5048A angleSensor1(PB_8, true);
// AS5048A angleSensor2(PB_9, true);

int txMsgID = 0x069;
int rxMsgID = 0x06a; // needed for rx filtering

uint8_t txData[8]{0x00, 0x01, 0x23, 0x45, 0xab, 0xcd, 0xef, 0xff};
uint8_t txDataLen = 8;
uint32_t txDly = 500; // mSec

uint16_t command = 0b1111111111111111; // read command (0xFFF)
uint16_t rawData = 0;                  // bits from the encoder (16 bits, but top 2 has to be discarded)
float degAngle_1 = 0;                  // Angle1 in degrees
float degAngle_2 = 0;                  // Angle2 in degrees

int id, fltIdx;
uint8_t rxbytes[8];

// Can setup
// eXoCAN can(STD_ID_LEN, BR500K, PORTA_11_12_WIRE);

eXoCAN can;

int pos_1, pos_2;
int tgt_1, tgt_2, ch, motor_1, motor_2, req_id;

#define AVE_NUM 30 // 　移動平均サンプル数

#define MOTOR_DZ 5 // モーター不感帯　(Dead Zone)

uint16_t ave1[AVE_NUM], ave2[AVE_NUM];
uint16_t rawData1, rawData2;

int ave_count = 0;

bool send_can_message = false;

void move_ave()
{
  uint32_t sum1 = 0;
  uint32_t sum2 = 0;

  uint16_t ave_res1 = 0;
  uint16_t ave_res2 = 0;

  ave1[ave_count] = rawData1;
  ave2[ave_count] = rawData2;

  ave_count++;
  if (ave_count == AVE_NUM)
    ave_count = 0;

  for (int i = 0; i < AVE_NUM; i++)
  {
    sum1 += ave1[i];
    sum2 += ave2[i];
  }

  ave_res1 = sum1 / AVE_NUM;
  ave_res2 = sum2 / AVE_NUM;

  degAngle_1 = (float)ave_res1 / 16384.0 * 360.0; // 16384 = 2^14, 360 = 360 degrees
  degAngle_2 = (float)ave_res2 / 16384.0 * 360.0; // 16384 = 2^14, 360 = 360 degrees

  pos_1 = (int)degAngle_1;
  pos_2 = (int)degAngle_2;
  // pos_1 = (int)rawData1  / 16384.0 * 360.0; // 16384 = 2^14, 360 = 360 degrees
  // pos_2 = (int)rawData2  / 16384.0 * 360.0; // 16384 = 2^14, 360 = 360 degrees
}

// Read can Function
inline void canRead(bool print = false)
{
  if (can.rxMsgLen >= 0)
  {
    if (print)
    {
      if (can.id == rxMsgID)
      {                                 // if statement catches any missed by filter.
        ch = (can.rxData.bytes[0]);     // first byte is for idiot light

        // Serial2.println(ch);

        int m1 = (can.rxData.bytes[1]); // next 3 are added to make the 635 steps of the stepper motor
        int m2 = (can.rxData.bytes[2]);
        int m3 = (can.rxData.bytes[3]);
        int m4 = (can.rxData.bytes[4]);


        switch (ch)
        {
        case 0:
          tgt_1 = pos_1;
          tgt_2 = pos_2;
          req_id = 0;
          break;

        case 1:
          tgt_1 = m2 +(255 * m1);
          tgt_2 = m4 +(255 * m3);
          req_id = 1;
          break;

        case 9:
          
          send_can_message = true;

          req_id = 9;
          break;

  
        }
      }

  
      can.rxMsgLen = -1;
    }
    // return id;
  }
}

void canISR() // get bus msg frame passed by a filter to FIFO0
{
  // can.filterMask16Init(0, txMsgID, 0x7ff, rxMsgID, 0x7ff);      // supposed to filter messages... always misses the first wrong one
  can.rxMsgLen = can.receive(can.id, fltIdx, can.rxData.bytes); // get CAN msg
  
  Serial2.print("CAN_recived!:");
  Serial2.println(can.id);


}

void readRegister(int cs)
{
  SPI.beginTransaction(SPISettings(100000, MSBFIRST, SPI_MODE1));

  //--sending the command

  if (cs == 0)
  {
    digitalWrite(CS1Pin, LOW);
    SPI.transfer16(command);
    digitalWrite(CS1Pin, HIGH);

    delay(10);

    //--receiving the reading
    digitalWrite(CS1Pin, LOW);
    rawData = SPI.transfer16(command);
    digitalWrite(CS1Pin, HIGH);
    SPI.endTransaction();
    delay(10);

    rawData = rawData & 0b0011111111111111; // removing the top 2 bits (PAR and EF)

    rawData1 = rawData;

    // degAngle_1 = (float)rawData / 16384.0 * 360.0; // 16384 = 2^14, 360 = 360 degrees
  }
  else
  {

    digitalWrite(CS2Pin, LOW);
    SPI.transfer16(command);
    digitalWrite(CS2Pin, HIGH);

    delay(10);

    //--receiving the reading
    digitalWrite(CS2Pin, LOW);
    rawData = SPI.transfer16(command);
    digitalWrite(CS2Pin, HIGH);
    SPI.endTransaction();
    delay(10);

    rawData = rawData & 0b0011111111111111; // removing the top 2 bits (PAR and EF)

    rawData2 = rawData;

    // degAngle_2 = (float)rawData / 16384.0 * 360.0; // 16384 = 2^14, 360 = 360 degrees
  }

  // Serial.print("Deg: ");
  // Serial.println(degAngle);
}

void motor_cmd(bool ch, bool Dg, bool Pw)
{
  if (ch)
  {
    digitalWrite(M1_D, Dg);
    digitalWrite(M1_P, Pw);
  }
  else
  {
    digitalWrite(M2_D, Dg);
    digitalWrite(M2_P, Pw);
  }
}

void motor_work()
{
  int diff;

  diff = abs(pos_1 - tgt_1);
  if (diff >= MOTOR_DZ)
  {
    if (pos_1 > tgt_1)
    {
      motor_cmd(0, 1, 1); // up
    }
    else
    {
      motor_cmd(0, 0, 1); // down
    }
  }
  else
  {
    motor_cmd(0, 0, 0); // stop
  }

  diff = abs(pos_2 - tgt_2);
  if (diff >= 5)
  {
    if (pos_2 > tgt_2)
    {
      motor_cmd(1, 0, 1); // up
    }
    else
    {
      motor_cmd(1, 1, 1); // down
    }
  }
  else
  {
    motor_cmd(1, 0, 0); // stop
  }
}

void set_candata()
{

  txData[0] = 0x00;
  txData[1] = highByte(pos_1);
  txData[2] = lowByte(pos_1);
  txData[3] = highByte(pos_2);
  txData[4] = lowByte(pos_2);
  txData[5] = 0xff;
  txData[6] = 0xff;
  txData[7] = 0xff;
}

void setup()
{
  can.begin(STD_ID_LEN, BR500K, PORTA_11_12_XCVR); // 11b IDs, 250k bit rate, no transceiver chip, portA pins 11,12
  // can.begin(STD_ID_LEN, BR500K, PORTA_11_12_WIRE_PULLUP);
  can.filterMask16Init(0, 0, 0x7ff, 0, 0); // filter bank 0, filter 0: don't pass any, flt 1: pass all msgs
  can.attachInterrupt(canISR);
  // can.enableInterrupt();

  pinMode(bluePillLED, OUTPUT);
  pinMode(CS1Pin, OUTPUT);
  pinMode(CS2Pin, OUTPUT);
  digitalWrite(CS1Pin, HIGH);
  digitalWrite(CS2Pin, HIGH);

  pinMode(M1_D, OUTPUT);
  pinMode(M1_P, OUTPUT);
  pinMode(M2_D, OUTPUT);
  pinMode(M2_P, OUTPUT);

  digitalWrite(M1_D, LOW);
  digitalWrite(M1_P, LOW);
  digitalWrite(M2_D, LOW);
  digitalWrite(M2_P, LOW);

  Serial2.begin(115200);

  Serial2.println("start");

  SPI.begin();

  delay(100);

  for (int i = 0; i < 100; i++)
  {

    readRegister(0);
    readRegister(1);
    move_ave();
  }

  tgt_1 = pos_1;
  tgt_2 = pos_2;

}





uint32_t last = 0;
void loop()
{
  // if (millis() / txDly != last) // tx every txDly
  // {
  //   last = millis() / txDly;

  //   set_candata();
  //   can.transmit(txMsgID, txData, txDataLen);
  // }

  if( send_can_message)
  {
    set_candata();
    can.transmit(txMsgID, txData, txDataLen);

    send_can_message = false;

  }

  // if (can.receive(id, fltIdx, rxbytes) > -1) // poll for rx
  // {
    
  //   Serial2.println("CAN_recived!");
  //   digitalToggle(bluePillLED);
  // }

  // float val1 = angleSensor1.getRawRotation();
  // float val2 = angleSensor2.getRotationInDegrees();

  readRegister(0); // read the position of the magnet
  readRegister(1); // read the position of the magnet

  move_ave();

  Serial2.print(pos_1);
  Serial2.print(" / ");
  Serial2.print(tgt_1);

  Serial2.print("\t");

  Serial2.print(pos_2);
  Serial2.print(" / ");
  Serial2.print(tgt_2);

  Serial2.print("\r\n");

  // Serial2.print(degAngle_1);
  // Serial2.print("\t");
  // Serial2.println(degAngle_2);

  // digitalToggle(bluePillLED);

  canRead(true);
  motor_work();
  

  // delay(10；

  // motor_cmd(0, 0, 1);
  // motor_cmd(1, 0, 1);
  // delay(5000);

  // motor_cmd(0, 0, 0);
  // motor_cmd(1, 0, 0);
  // delay(5000);
}