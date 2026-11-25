// =====================================================================
//  CubeSat 3U - example SysML v2 model
//  Project : sysml-to-knowledge-graph
//  Purpose : a small but complete model (parts, attributes, ports,
//            connections, requirements) used as input for the
//            SysML v2 -> knowledge graph mapper.
//  Note    : values are realistic examples, not data of a real mission.
// =====================================================================

package CubeSatModel {

    private import ScalarValues::*;   // Real, Integer, String ...
    private import ISQ::*;            // quantity types: MassValue, PowerValue ...
    private import SI::*;             // units: kg, W, J, V, s ...

    // -----------------------------------------------------------------
    // 1. PORT DEFINITIONS  (the "socket standards")
    // -----------------------------------------------------------------
    port def PowerPort {
        doc /* Electrical power interface. 'out' = power leaves the part. */
        out attribute voltage : ElectricPotentialValue;
    }

    port def DataPort {
        doc /* Data interface. 'out' = data leaves the part. */
        out attribute dataRate : Real;   // kbps (kilobits per second)
    }
    // A port typed '~PowerPort' or '~DataPort' is CONJUGATED:
    // same port definition, but every direction is flipped (out -> in).

    // -----------------------------------------------------------------
    // 2. PART DEFINITIONS  (the "blueprints")
    // -----------------------------------------------------------------
    part def Structure {
        doc /* 3U aluminium frame (10 x 10 x 34 cm) that holds all parts. */
        attribute mass : MassValue;
    }

    part def SolarPanel {
        doc /* Deployable solar panel that converts sunlight into power. */
        attribute mass : MassValue;
        attribute powerOutput : PowerValue;
        port powerOut : PowerPort;
    }

    part def Battery {
        doc /* Li-ion battery that stores energy for eclipse periods. */
        attribute mass : MassValue;
        attribute capacity : EnergyValue;          // 1 Wh = 3600 J
        port powerIn  : ~PowerPort;                // charged by solar panels
        port powerOut : PowerPort;                 // supplies the other parts
    }

    part def OnBoardComputer {
        doc /* OBC: the 'brain' that controls all subsystems. */
        attribute mass : MassValue;
        attribute powerConsumption : PowerValue;
        port powerIn : ~PowerPort;
        port imageIn : ~DataPort;                  // receives photos from the camera
        port dataOut : DataPort;                   // sends data to the radio
    }

    part def Radio {
        doc /* UHF radio that sends data to the ground station. */
        attribute mass : MassValue;
        attribute powerConsumption : PowerValue;
        attribute downlinkRate : Real;             // kbps
        port powerIn : ~PowerPort;
        port dataIn  : ~DataPort;
    }

    part def Camera {
        doc /* Earth-observation camera (the payload). */
        attribute mass : MassValue;
        attribute powerConsumption : PowerValue;
        port powerIn  : ~PowerPort;
        port imageOut : DataPort;
    }

    part def CubeSat {
        doc /* The whole satellite (system of interest). */
        attribute totalMass : MassValue;
    }

    // -----------------------------------------------------------------
    // 3. THE SYSTEM: usages, attribute values and connections
    // -----------------------------------------------------------------
    part cubeSat : CubeSat {

        part structure : Structure {
            attribute :>> mass = 1.0 [kg];
        }
        part leftPanel : SolarPanel {
            attribute :>> mass = 0.2 [kg];
            attribute :>> powerOutput = 7.0 [W];
        }
        part rightPanel : SolarPanel {
            attribute :>> mass = 0.2 [kg];
            attribute :>> powerOutput = 7.0 [W];
        }
        part battery : Battery {
            attribute :>> mass = 0.3 [kg];
            attribute :>> capacity = 72000.0 [J];  // = 20 Wh
        }
        part obc : OnBoardComputer {
            attribute :>> mass = 0.1 [kg];
            attribute :>> powerConsumption = 1.5 [W];
        }
        part radio : Radio {
            attribute :>> mass = 0.15 [kg];
            attribute :>> powerConsumption = 2.0 [W];
            attribute :>> downlinkRate = 9.6;
        }
        part camera : Camera {
            attribute :>> mass = 0.25 [kg];
            attribute :>> powerConsumption = 2.5 [W];
        }

        // Derived value: total mass is the sum of all parts (used by R1)
        attribute :>> totalMass = structure.mass + leftPanel.mass + rightPanel.mass
                                + battery.mass + obc.mass + radio.mass + camera.mass;

        // Power connections (the "cables")
        connect leftPanel.powerOut  to battery.powerIn;
        connect rightPanel.powerOut to battery.powerIn;
        connect battery.powerOut    to obc.powerIn;
        connect battery.powerOut    to radio.powerIn;
        connect battery.powerOut    to camera.powerIn;

        // Data connections: photo goes camera -> obc -> radio -> Earth
        connect camera.imageOut to obc.imageIn;
        connect obc.dataOut     to radio.dataIn;

        // Behaviour of the whole satellite (see section 9)
        exhibit state operatingModes : OperatingModes;
    }

    // -----------------------------------------------------------------
    // 4. REQUIREMENTS
    // -----------------------------------------------------------------
    requirement def MassRequirement {
        doc /* The total mass of the satellite shall not exceed the limit. */
        subject sat : CubeSat;
        attribute massLimit : MassValue;
        require constraint { sat.totalMass <= massLimit }
    }

    requirement def EclipsePowerRequirement {
        doc /* The battery shall supply the load during the whole eclipse. */
        subject bat : Battery;
        attribute loadPower : PowerValue;
        attribute eclipseDuration : DurationValue;
        require constraint { bat.capacity >= loadPower * eclipseDuration }
    }

    requirement r1_mass : MassRequirement {
        attribute :>> massLimit = 4.0 [kg];
    }

    requirement r2_eclipsePower : EclipsePowerRequirement {
        attribute :>> loadPower = 6.0 [W];          // obc + radio + camera
        attribute :>> eclipseDuration = 2700.0 [s]; // 45 minutes
    }

    requirement r3_imageDownlink {
        doc /* The satellite shall take an Earth image and send it to the ground station. */
    }

    requirement r4_thermalRange {
        doc /* The internal temperature shall stay between -20 and 60 degC. */
    }

    // -----------------------------------------------------------------
    // 5. SATISFY RELATIONS  (who is responsible for which requirement)
    // -----------------------------------------------------------------
    satisfy r1_mass by cubeSat;
    satisfy r2_eclipsePower by cubeSat.battery;
    satisfy r3_imageDownlink by cubeSat.camera;
    satisfy r3_imageDownlink by cubeSat.radio;
    // r4_thermalRange is intentionally NOT satisfied by any part.
    // The knowledge graph must detect this gap (see queries in step 8).

    // -----------------------------------------------------------------
    // 6. VERIFICATION CASES  (which test checks which requirement)
    // -----------------------------------------------------------------
    verification def MassTest {
        doc /* Weigh the fully assembled satellite on a calibrated scale. */
        subject testSat : CubeSat;
        objective { verify r1_mass; }
    }

    verification def EclipseDischargeTest {
        doc /* Run OBC, radio and camera from the battery only for 45 minutes. */
        subject testBattery : Battery;
        objective { verify r2_eclipsePower; }
    }

    verification def EndToEndDownlinkTest {
        doc /* Take an image and receive it at a test ground station. */
        subject testSat : CubeSat;
        objective { verify r3_imageDownlink; }
    }

    verification def ThermalVacuumTest {
        doc /* Test the satellite in a thermal vacuum chamber (-20 to 60 degC). */
        subject testSat : CubeSat;
        objective { verify r4_thermalRange; }
    }

    verification massTest : MassTest;
    verification eclipseDischargeTest : EclipseDischargeTest;
    verification endToEndDownlinkTest : EndToEndDownlinkTest;
    verification thermalVacuumTest : ThermalVacuumTest;

    // -----------------------------------------------------------------
    // 7. ITEMS AND SIGNALS  (things that flow or trigger behaviour)
    // -----------------------------------------------------------------
    item def Image {
        doc /* Raw Earth image taken by the camera. */
    }
    item def DataPacket {
        doc /* Compressed image packet ready for downlink. */
    }
    attribute def ImagingCommand  { doc /* Command from the ground: take an image. */ }
    attribute def PowerOk         { doc /* Battery is charged enough for normal work. */ }
    attribute def BatteryLow      { doc /* Battery charge is below the safe limit. */ }
    attribute def ImageSent       { doc /* The image packet was sent to the ground. */ }

    // -----------------------------------------------------------------
    // 8. USE CASE  (who uses the satellite and why)
    // -----------------------------------------------------------------
    part def Operator {
        doc /* Person at the ground station who commands the satellite. */
    }
    part def GroundStation {
        doc /* Antenna on Earth that receives the satellite data. */
    }

    use case def ObtainEarthImage {
        doc /* The operator requests an Earth image and receives it on the ground. */
        subject sat : CubeSat;
        actor operator : Operator;
        actor groundStation : GroundStation;
        objective {
            doc /* An Earth image is available at the ground station. */
        }
    }
    use case obtainEarthImage : ObtainEarthImage;

    // -----------------------------------------------------------------
    // 9. BEHAVIOUR: ACTIVITY  (the imaging task step by step)
    // -----------------------------------------------------------------
    action def CaptureImage {
        doc /* Camera takes a raw Earth image. */
        out item image : Image;
    }
    action def ProcessImage {
        doc /* OBC compresses the image into a data packet. */
        in item image : Image;
        out item packet : DataPacket;
    }
    action def DownlinkImage {
        doc /* Radio sends the packet to the ground station. */
        in item packet : DataPacket;
    }

    action def ImagingTask {
        doc /* Take an image, compress it and send it to Earth. */
        action capture  : CaptureImage;
        action process  : ProcessImage;
        action downlink : DownlinkImage;
        first start then capture;
        first capture then process;
        first process then downlink;
        first downlink then done;
    }
    action imagingTask : ImagingTask;

    // Allocation: which part performs which step (function -> hardware)
    allocate imagingTask.capture  to cubeSat.camera;
    allocate imagingTask.process  to cubeSat.obc;
    allocate imagingTask.downlink to cubeSat.radio;

    // -----------------------------------------------------------------
    // 10. BEHAVIOUR: STATES  (operating modes of the satellite)
    // -----------------------------------------------------------------
    state def OperatingModes {
        doc /* Safe mode protects the satellite when power is low. */
        entry; then safeMode;

        state safeMode;
        state nominalMode;
        state imagingMode;

        transition safe_to_nominal
            first safeMode accept PowerOk then nominalMode;
        transition nominal_to_imaging
            first nominalMode accept ImagingCommand then imagingMode;
        transition imaging_to_nominal
            first imagingMode accept ImageSent then nominalMode;
        transition nominal_to_safe
            first nominalMode accept BatteryLow then safeMode;
        transition imaging_to_safe
            first imagingMode accept BatteryLow then safeMode;
    }

    // -----------------------------------------------------------------
    // 11. BEHAVIOUR: SEQUENCE  (messages over time in one scenario)
    // -----------------------------------------------------------------
    occurrence def ImagingScenario {
        doc /* One imaging pass: command goes up, image comes down. */
        part operator : Operator {
            event occurrence sendCommand;
            event occurrence receiveImage;
        }
        part groundStation : GroundStation {
            event occurrence receiveCommand;
            event occurrence uplinkCommand;
            event occurrence receivePacket;
            event occurrence deliverImage;
        }
        part sat : CubeSat {
            event occurrence receiveCommand;
            event occurrence sendPacket;
        }
        message requestMsg of ImagingCommand
            from operator.sendCommand to groundStation.receiveCommand;
        message uplinkMsg of ImagingCommand
            from groundStation.uplinkCommand to sat.receiveCommand;
        message downlinkMsg of DataPacket
            from sat.sendPacket to groundStation.receivePacket;
        message deliverMsg of Image
            from groundStation.deliverImage to operator.receiveImage;
        first requestMsg then uplinkMsg;
        first uplinkMsg then downlinkMsg;
        first downlinkMsg then deliverMsg;
    }
}
