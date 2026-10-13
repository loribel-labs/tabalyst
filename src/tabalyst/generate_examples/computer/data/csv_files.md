### brand.csv

```csv
id,en,fr
amd,AMD,AMD
aspeed,ASPEED,ASPEED
broadcom,Broadcom,Broadcom
intel,Intel,Intel
nvidia,NVIDIA,NVIDIA
raspberry_pi,Raspberry Pi,Raspberry Pi
acer,Acer,Acer
apple,Apple,Apple
asus,ASUS,ASUS
dell,Dell,Dell
framework,Framework,Framework
gigabyte,GIGABYTE,GIGABYTE
hp,HP,HP
hpe,HPE,HPE
lenovo,Lenovo,Lenovo
lg,LG,LG
microsoft,Microsoft,Microsoft
msi,MSI,MSI
razer,Razer,Razer
samsung,Samsung,Samsung
supermicro,Supermicro,Supermicro
zotac,ZOTAC,ZOTAC
```

---

### color.csv

```csv
id,en,fr
black,Black,Noir
white,White,Blanc
silver,Silver,Argent
gray,Gray,Gris
dark_gray,Dark gray,Gris foncé
graphite,Graphite,Graphite
space_gray,Space gray,Gris sidéral
blue,Blue,Bleu
navy,Navy,Marine
green,Green,Vert
red,Red,Rouge
gold,Gold,Or
rose_gold,Rose gold,Or rose
beige,Beige,Beige
purple,Purple,Violet
```

---

### computer_type.csv

```csv
id,en,fr,weight
laptop,Laptop,Ordinateur portable,1
desktop,Desktop,Ordinateur de bureau,1
all_in_one,All-in-One,Tout-en-un,1
mini_pc,Mini PC,Mini PC,1
single_board_computer,Single-board computer,Ordinateur monocarte,1
server,Server,Serveur,1
```

---

### computer_type_form_factor.csv

```csv
computer_type_id,form_factor_id
laptop,clamshell
laptop,convertible_360
laptop,detachable
laptop,rugged
desktop,tower
desktop,small_form_factor
desktop,micro
all_in_one,integrated_display
mini_pc,mini
mini_pc,micro
mini_pc,stick
single_board_computer,board
server,tower
server,rackmount
server,blade
```

---

### computer_type_product_segment.csv

```csv
computer_type_id,product_segment_id
laptop,general_purpose
laptop,consumer
laptop,business
laptop,premium
laptop,gaming
laptop,workstation
laptop,creator
laptop,education
laptop,enterprise
laptop,thin_client
desktop,general_purpose
desktop,consumer
desktop,business
desktop,premium
desktop,gaming
desktop,workstation
desktop,creator
desktop,education
desktop,enterprise
desktop,thin_client
all_in_one,general_purpose
all_in_one,consumer
all_in_one,business
all_in_one,premium
all_in_one,creator
all_in_one,education
mini_pc,general_purpose
mini_pc,consumer
mini_pc,business
mini_pc,premium
mini_pc,gaming
mini_pc,workstation
mini_pc,creator
mini_pc,education
mini_pc,enterprise
mini_pc,thin_client
single_board_computer,general_purpose
single_board_computer,consumer
single_board_computer,education
single_board_computer,enterprise
server,business
server,workstation
server,enterprise
```

---

### cpu.csv

```csv
id,en,fr,brand_id,family,model,architecture,cores,threads,max_clock_ghz,npu_tops,npu_brand,npu_family
apple_m3,Apple M3,Apple M3,apple,apple_m3,M3,arm64,8,8,4.0,18,apple,apple_neural_engine
apple_m4,Apple M4,Apple M4,apple,apple_m4,M4,arm64,10,10,4.4,38,apple,apple_neural_engine
apple_m4_pro,Apple M4 Pro,Apple M4 Pro,apple,apple_m4_pro,M4 Pro,arm64,12,12,4.5,38,apple,apple_neural_engine
apple_m4_max,Apple M4 Max,Apple M4 Max,apple,apple_m4_max,M4 Max,arm64,14,14,4.5,38,apple,apple_neural_engine
apple_m2_ultra,Apple M2 Ultra,Apple M2 Ultra,apple,apple_m2_ultra,M2 Ultra,arm64,24,24,3.7,31,apple,apple_neural_engine
intel_xeon_silver_4510,Intel Xeon Silver 4510,Intel Xeon Silver 4510,intel,intel_xeon_silver,4510,x86_64,12,24,3.3,0,,
broadcom_bcm2712,Broadcom BCM2712,Broadcom BCM2712,broadcom,broadcom_bcm2712,BCM2712,arm64,4,4,2.4,0,,
intel_core_ultra_5_225u,Intel Core Ultra 5 225U,Intel Core Ultra 5 225U,intel,intel_core_ultra_5,225U,x86_64,12,14,4.8,12,intel,intel_ai_boost
intel_core_ultra_5_245,Intel Core Ultra 5 245,Intel Core Ultra 5 245,intel,intel_core_ultra_5,245,x86_64,14,14,5.1,13,intel,intel_ai_boost
intel_core_ultra_7_258v,Intel Core Ultra 7 258V,Intel Core Ultra 7 258V,intel,intel_core_ultra_7,258V,x86_64,8,8,4.8,47,intel,intel_ai_boost
intel_core_ultra_7_265,Intel Core Ultra 7 265,Intel Core Ultra 7 265,intel,intel_core_ultra_7,265,x86_64,20,20,5.3,13,intel,intel_ai_boost
intel_core_ultra_9_285,Intel Core Ultra 9 285,Intel Core Ultra 9 285,intel,intel_core_ultra_9,285,x86_64,24,24,5.6,13,intel,intel_ai_boost
intel_core_ultra_9_285hx,Intel Core Ultra 9 285HX,Intel Core Ultra 9 285HX,intel,intel_core_ultra_9,285HX,x86_64,24,24,5.5,13,intel,intel_ai_boost
amd_ryzen_7_8840u,AMD Ryzen 7 8840U,AMD Ryzen 7 8840U,amd,amd_ryzen_7,8840U,x86_64,8,16,5.1,16,amd,amd_ryzen_ai
amd_ryzen_ai_7_350,AMD Ryzen AI 7 350,AMD Ryzen AI 7 350,amd,amd_ryzen_ai_7,350,x86_64,8,16,5.0,50,amd,amd_ryzen_ai
amd_ryzen_ai_9_hx_370,AMD Ryzen AI 9 HX 370,AMD Ryzen AI 9 HX 370,amd,amd_ryzen_ai_9,HX 370,x86_64,12,24,5.1,50,amd,amd_ryzen_ai
amd_ryzen_9_9955hx,AMD Ryzen 9 9955HX,AMD Ryzen 9 9955HX,amd,amd_ryzen_9,9955HX,x86_64,16,32,5.4,0,,
```

---

### cpu_memory_weight.csv

```csv
cpu_id,memory_id,weight
intel_core_ultra_5_225u,ddr5_8gb,1
intel_core_ultra_5_225u,ddr5_16gb,5
intel_core_ultra_5_225u,ddr5_24gb,3
intel_core_ultra_5_225u,ddr5_32gb,5
intel_core_ultra_5_225u,ddr5_48gb,2
intel_core_ultra_5_225u,ddr5_64gb,1
intel_core_ultra_5_225u,lpddr5x_16gb,5
intel_core_ultra_5_225u,lpddr5x_24gb,3
intel_core_ultra_5_225u,lpddr5x_32gb,5
intel_core_ultra_5_225u,lpddr5x_64gb,1
intel_core_ultra_5_245,ddr5_8gb,1
intel_core_ultra_5_245,ddr5_16gb,6
intel_core_ultra_5_245,ddr5_24gb,3
intel_core_ultra_5_245,ddr5_32gb,5
intel_core_ultra_5_245,ddr5_48gb,2
intel_core_ultra_5_245,ddr5_64gb,2
intel_core_ultra_5_245,ddr5_96gb,1
intel_core_ultra_7_258v,lpddr5x_16gb,3
intel_core_ultra_7_258v,lpddr5x_24gb,4
intel_core_ultra_7_258v,lpddr5x_32gb,6
intel_core_ultra_7_258v,lpddr5x_64gb,3
intel_core_ultra_7_265,ddr5_16gb,2
intel_core_ultra_7_265,ddr5_24gb,2
intel_core_ultra_7_265,ddr5_32gb,6
intel_core_ultra_7_265,ddr5_48gb,4
intel_core_ultra_7_265,ddr5_64gb,5
intel_core_ultra_7_265,ddr5_96gb,2
intel_core_ultra_7_265,ddr5_128gb,1
intel_core_ultra_9_285,ddr5_16gb,1
intel_core_ultra_9_285,ddr5_32gb,4
intel_core_ultra_9_285,ddr5_48gb,3
intel_core_ultra_9_285,ddr5_64gb,6
intel_core_ultra_9_285,ddr5_96gb,4
intel_core_ultra_9_285,ddr5_128gb,3
intel_core_ultra_9_285,ddr5_192gb,1
intel_core_ultra_9_285hx,ddr5_16gb,1
intel_core_ultra_9_285hx,ddr5_32gb,5
intel_core_ultra_9_285hx,ddr5_48gb,3
intel_core_ultra_9_285hx,ddr5_64gb,6
intel_core_ultra_9_285hx,ddr5_96gb,3
intel_core_ultra_9_285hx,ddr5_128gb,1
amd_ryzen_7_8840u,ddr5_8gb,1
amd_ryzen_7_8840u,ddr5_16gb,5
amd_ryzen_7_8840u,ddr5_32gb,5
amd_ryzen_7_8840u,ddr5_64gb,2
amd_ryzen_7_8840u,lpddr5x_16gb,5
amd_ryzen_7_8840u,lpddr5x_24gb,3
amd_ryzen_7_8840u,lpddr5x_32gb,5
amd_ryzen_7_8840u,lpddr5x_64gb,2
amd_ryzen_ai_7_350,ddr5_16gb,3
amd_ryzen_ai_7_350,ddr5_24gb,2
amd_ryzen_ai_7_350,ddr5_32gb,6
amd_ryzen_ai_7_350,ddr5_48gb,3
amd_ryzen_ai_7_350,ddr5_64gb,4
amd_ryzen_ai_7_350,lpddr5x_16gb,3
amd_ryzen_ai_7_350,lpddr5x_24gb,3
amd_ryzen_ai_7_350,lpddr5x_32gb,6
amd_ryzen_ai_7_350,lpddr5x_64gb,4
amd_ryzen_ai_9_hx_370,ddr5_16gb,1
amd_ryzen_ai_9_hx_370,ddr5_32gb,5
amd_ryzen_ai_9_hx_370,ddr5_48gb,4
amd_ryzen_ai_9_hx_370,ddr5_64gb,6
amd_ryzen_ai_9_hx_370,ddr5_96gb,2
amd_ryzen_ai_9_hx_370,lpddr5x_16gb,1
amd_ryzen_ai_9_hx_370,lpddr5x_24gb,2
amd_ryzen_ai_9_hx_370,lpddr5x_32gb,5
amd_ryzen_ai_9_hx_370,lpddr5x_64gb,6
amd_ryzen_9_9955hx,ddr5_16gb,1
amd_ryzen_9_9955hx,ddr5_32gb,5
amd_ryzen_9_9955hx,ddr5_48gb,3
amd_ryzen_9_9955hx,ddr5_64gb,6
amd_ryzen_9_9955hx,ddr5_96gb,4
amd_ryzen_9_9955hx,ddr5_128gb,2
```

---

### cpu_operating_system.csv

```csv
cpu_id,operating_system_id
apple_m3,macos
apple_m4,macos
apple_m4_pro,macos
apple_m4_max,macos
apple_m2_ultra,macos
intel_xeon_silver_4510,ubuntu
intel_xeon_silver_4510,debian
broadcom_bcm2712,raspberry_pi_os
intel_core_ultra_5_225u,windows_11_home
intel_core_ultra_5_225u,windows_11_pro
intel_core_ultra_5_225u,windows_11_education
intel_core_ultra_5_225u,ubuntu
intel_core_ultra_5_225u,fedora
intel_core_ultra_5_225u,debian
intel_core_ultra_5_225u,linux_mint
intel_core_ultra_5_225u,no_os
intel_core_ultra_5_245,windows_11_home
intel_core_ultra_5_245,windows_11_pro
intel_core_ultra_5_245,windows_11_education
intel_core_ultra_5_245,ubuntu
intel_core_ultra_5_245,fedora
intel_core_ultra_5_245,debian
intel_core_ultra_5_245,linux_mint
intel_core_ultra_5_245,no_os
intel_core_ultra_7_258v,windows_11_home
intel_core_ultra_7_258v,windows_11_pro
intel_core_ultra_7_258v,windows_11_education
intel_core_ultra_7_258v,ubuntu
intel_core_ultra_7_258v,fedora
intel_core_ultra_7_258v,debian
intel_core_ultra_7_258v,linux_mint
intel_core_ultra_7_258v,no_os
intel_core_ultra_7_265,windows_11_home
intel_core_ultra_7_265,windows_11_pro
intel_core_ultra_7_265,windows_11_education
intel_core_ultra_7_265,ubuntu
intel_core_ultra_7_265,fedora
intel_core_ultra_7_265,debian
intel_core_ultra_7_265,linux_mint
intel_core_ultra_7_265,no_os
intel_core_ultra_9_285,windows_11_home
intel_core_ultra_9_285,windows_11_pro
intel_core_ultra_9_285,windows_11_pro_workstations
intel_core_ultra_9_285,ubuntu
intel_core_ultra_9_285,fedora
intel_core_ultra_9_285,debian
intel_core_ultra_9_285,linux_mint
intel_core_ultra_9_285,no_os
intel_core_ultra_9_285hx,windows_11_home
intel_core_ultra_9_285hx,windows_11_pro
intel_core_ultra_9_285hx,windows_11_pro_workstations
intel_core_ultra_9_285hx,ubuntu
intel_core_ultra_9_285hx,fedora
intel_core_ultra_9_285hx,debian
intel_core_ultra_9_285hx,linux_mint
intel_core_ultra_9_285hx,no_os
amd_ryzen_7_8840u,windows_11_home
amd_ryzen_7_8840u,windows_11_pro
amd_ryzen_7_8840u,windows_11_education
amd_ryzen_7_8840u,ubuntu
amd_ryzen_7_8840u,fedora
amd_ryzen_7_8840u,debian
amd_ryzen_7_8840u,linux_mint
amd_ryzen_7_8840u,no_os
amd_ryzen_ai_7_350,windows_11_home
amd_ryzen_ai_7_350,windows_11_pro
amd_ryzen_ai_7_350,windows_11_education
amd_ryzen_ai_7_350,ubuntu
amd_ryzen_ai_7_350,fedora
amd_ryzen_ai_7_350,debian
amd_ryzen_ai_7_350,linux_mint
amd_ryzen_ai_7_350,no_os
amd_ryzen_ai_9_hx_370,windows_11_home
amd_ryzen_ai_9_hx_370,windows_11_pro
amd_ryzen_ai_9_hx_370,windows_11_pro_workstations
amd_ryzen_ai_9_hx_370,ubuntu
amd_ryzen_ai_9_hx_370,fedora
amd_ryzen_ai_9_hx_370,debian
amd_ryzen_ai_9_hx_370,linux_mint
amd_ryzen_ai_9_hx_370,no_os
amd_ryzen_9_9955hx,windows_11_home
amd_ryzen_9_9955hx,windows_11_pro
amd_ryzen_9_9955hx,windows_11_pro_workstations
amd_ryzen_9_9955hx,ubuntu
amd_ryzen_9_9955hx,fedora
amd_ryzen_9_9955hx,debian
amd_ryzen_9_9955hx,linux_mint
amd_ryzen_9_9955hx,no_os
```

---

### display.csv

```csv
id,en,fr,display_type,touch,size_in,resolution,refresh_rate_hz,brightness_nits,finish,aspect_ratio,hdr,color_gamut
ips_15_3_2880_1864_60,15.3-inch 2880x1864 IPS display,Écran IPS 15.3 po 2880x1864,ips,false,15.3,2880x1864,60,500,glossy,3:2,none,dci_p3_100
none,No integrated display,Aucun écran intégré,none,false,,,,,,,,
ips_11_6_hd_60,11.6-inch HD IPS display,Écran IPS HD 11.6 po,ips,false,11.6,1366x768,60,250,matte,16:9,none,srgb_62
ips_12_4_fhd_60_touch,12.4-inch Full HD IPS touchscreen,Écran tactile IPS Full HD 12.4 po,ips,true,12.4,1920x1080,60,300,glossy,16:9,none,srgb_100
ips_13_3_fhd_60,13.3-inch Full HD IPS display,Écran IPS Full HD 13.3 po,ips,false,13.3,1920x1080,60,300,matte,16:9,none,srgb_100
ips_13_3_fhd_60_touch,13.3-inch Full HD IPS touchscreen,Écran tactile IPS Full HD 13.3 po,ips,true,13.3,1920x1080,60,400,glossy,16:9,none,srgb_100
ips_13_6_2560_1664_60,13.6-inch 2560x1664 IPS display,Écran IPS 13.6 po 2560x1664,ips,false,13.6,2560x1664,60,500,glossy,16:10,hdr10,dci_p3_100
ips_14_wuxga_60,14-inch WUXGA IPS display,Écran IPS WUXGA 14 po,ips,false,14.0,1920x1200,60,300,matte,16:10,none,srgb_100
ips_14_wuxga_60_touch,14-inch WUXGA IPS touchscreen,Écran tactile IPS WUXGA 14 po,ips,true,14.0,1920x1200,60,400,glossy,16:10,none,srgb_100
ips_14_wuxga_120,14-inch WUXGA 120 Hz IPS display,Écran IPS WUXGA 120 Hz 14 po,ips,false,14.0,1920x1200,120,400,matte,16:10,none,srgb_100
ips_14_qhdplus_120,14-inch QHD+ 120 Hz IPS display,Écran IPS QHD+ 120 Hz 14 po,ips,false,14.0,2560x1600,120,500,matte,16:10,displayhdr_400,dci_p3_100
oled_14_2_8k_90,14-inch 2.8K OLED 90 Hz display,Écran OLED 2.8K 90 Hz 14 po,oled,false,14.0,2880x1800,90,400,glossy,16:10,true_black_500,dci_p3_100
oled_14_2_8k_120,14-inch 2.8K OLED 120 Hz display,Écran OLED 2.8K 120 Hz 14 po,oled,false,14.0,2880x1800,120,500,glossy,16:10,true_black_500,dci_p3_100
oled_14_2_8k_120_touch,14-inch 2.8K OLED 120 Hz touchscreen,Écran tactile OLED 2.8K 120 Hz 14 po,oled,true,14.0,2880x1800,120,500,glossy,16:10,true_black_500,dci_p3_100
ips_14_5_qhdplus_120,14.5-inch QHD+ 120 Hz IPS display,Écran IPS QHD+ 120 Hz 14.5 po,ips,false,14.5,2560x1600,120,500,matte,16:10,displayhdr_400,dci_p3_100
oled_14_5_3k_120_touch,14.5-inch 3K OLED 120 Hz touchscreen,Écran tactile OLED 3K 120 Hz 14.5 po,oled,true,14.5,3072x1920,120,500,glossy,16:10,true_black_500,dci_p3_100
ips_15_6_fhd_60,15.6-inch Full HD IPS display,Écran IPS Full HD 15.6 po,ips,false,15.6,1920x1080,60,250,matte,16:9,none,srgb_62
ips_15_6_fhd_144,15.6-inch Full HD 144 Hz IPS display,Écran IPS Full HD 144 Hz 15.6 po,ips,false,15.6,1920x1080,144,300,matte,16:9,none,srgb_100
ips_15_6_fhd_165,15.6-inch Full HD 165 Hz IPS display,Écran IPS Full HD 165 Hz 15.6 po,ips,false,15.6,1920x1080,165,350,matte,16:9,none,srgb_100
oled_15_6_2_8k_120,15.6-inch 2.8K OLED 120 Hz display,Écran OLED 2.8K 120 Hz 15.6 po,oled,false,15.6,2880x1800,120,500,glossy,16:10,true_black_500,dci_p3_100
ips_16_wuxga_60,16-inch WUXGA IPS display,Écran IPS WUXGA 16 po,ips,false,16.0,1920x1200,60,300,matte,16:10,none,srgb_100
ips_16_wuxga_120,16-inch WUXGA 120 Hz IPS display,Écran IPS WUXGA 120 Hz 16 po,ips,false,16.0,1920x1200,120,400,matte,16:10,none,srgb_100
ips_16_qhdplus_165,16-inch QHD+ 165 Hz IPS display,Écran IPS QHD+ 165 Hz 16 po,ips,false,16.0,2560x1600,165,500,matte,16:10,displayhdr_400,dci_p3_100
ips_16_qhdplus_240,16-inch QHD+ 240 Hz IPS display,Écran IPS QHD+ 240 Hz 16 po,ips,false,16.0,2560x1600,240,500,matte,16:10,displayhdr_400,dci_p3_100
oled_16_3_2k_120,16-inch 3.2K OLED 120 Hz display,Écran OLED 3.2K 120 Hz 16 po,oled,false,16.0,3200x2000,120,500,glossy,16:10,true_black_500,dci_p3_100
mini_led_16_qhdplus_240,16-inch QHD+ Mini-LED 240 Hz display,Écran Mini-LED QHD+ 240 Hz 16 po,mini_led,false,16.0,2560x1600,240,1000,matte,16:10,displayhdr_1000,dci_p3_100
ips_17_3_fhd_144,17.3-inch Full HD 144 Hz IPS display,Écran IPS Full HD 144 Hz 17.3 po,ips,false,17.3,1920x1080,144,300,matte,16:9,none,srgb_100
ips_17_3_qhd_240,17.3-inch QHD 240 Hz IPS display,Écran IPS QHD 240 Hz 17.3 po,ips,false,17.3,2560x1440,240,500,matte,16:9,displayhdr_400,dci_p3_100
ips_21_5_fhd_60,21.5-inch Full HD IPS display,Écran IPS Full HD 21.5 po,ips,false,21.5,1920x1080,60,250,matte,16:9,none,srgb_100
ips_23_8_fhd_60,23.8-inch Full HD IPS display,Écran IPS Full HD 23.8 po,ips,false,23.8,1920x1080,60,300,matte,16:9,none,srgb_100
ips_24_fhd_75,24-inch Full HD IPS display,Écran IPS Full HD 75 Hz 24 po,ips,false,24.0,1920x1080,75,300,matte,16:9,none,srgb_100
ips_27_qhd_60,27-inch QHD IPS display,Écran IPS QHD 27 po,ips,false,27.0,2560x1440,60,350,matte,16:9,none,srgb_100
ips_27_4k_60,27-inch 4K UHD IPS display,Écran IPS 4K UHD 27 po,ips,false,27.0,3840x2160,60,500,glossy,16:9,hdr10,dci_p3_95
ips_27_5k_60,27-inch 5K IPS display,Écran IPS 5K 27 po,ips,false,27.0,5120x2880,60,500,glossy,16:9,hdr10,dci_p3_100
oled_27_qhd_240,27-inch QHD OLED 240 Hz display,Écran OLED QHD 240 Hz 27 po,oled,false,27.0,2560x1440,240,1000,glossy,16:9,true_black_500,dci_p3_100
```

---

### extended_specs.csv

```csv
id,cellular_type,docking_support,thunderbolt_ports,displayport_ports,ethernet_port,card_reader_type,memory_slots_total,memory_slots_used,m2_slots_total,m2_slots_used,upgradeability_level,width_mm,depth_mm,height_mm,chassis_finish,microphone_type,speaker_configuration,keyboard_type,trusted_platform
aspire_5_a515_58m,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
swift_go_14_sfg14_73,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,312,221,15,aluminum,quad_array,quad_speaker,backlit_chiclet,tpm_2_0
travelmate_p4_14_tmp414_53,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
predator_helios_16_ph16_72,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
nitro_v_15_anv15_51,none,usb_c,0,1,true,sd,2,2,2,1,high,359,259,25,aluminum_plastic,dual_array,stereo,backlit_gaming,tpm_2_0
mac_mini_m4,none,usb_c,0,2,true,none,2,1,2,1,high,120,120,45,aluminum_plastic,none,none,external_keyboard,tpm_2_0
imac_24_m4,none,usb_c,0,1,true,sd,2,2,1,1,medium,540,190,420,aluminum_plastic,dual_array,stereo,wireless_keyboard,tpm_2_0
mac_studio_m4_max,none,thunderbolt_4,2,4,true,sd_uhsii,8,4,4,2,very_high,215,450,440,steel,none,none,professional_keyboard,tpm_2_0
mac_pro_m2_ultra,none,thunderbolt_4,2,4,true,sd_uhsii,8,4,4,2,very_high,215,450,440,steel,none,none,professional_keyboard,tpm_2_0
expertbook_b5_b5404,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
proart_p16_h7606,none,thunderbolt_4,2,1,true,sd_uhsii,2,2,2,1,high,359,253,21,aluminum,dual_array,stereo,backlit_chiclet,tpm_2_0
envy_16_2024,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,312,221,15,aluminum,quad_array,quad_speaker,backlit_chiclet,tpm_2_0
victus_16_2024,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
thinkbook_14_gen7,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
loq_15_gen9,none,usb_c,0,1,true,sd,2,2,2,1,high,359,259,25,aluminum_plastic,dual_array,stereo,backlit_gaming,tpm_2_0
thinkstation_p3_tower_gen2,none,thunderbolt_4,2,4,true,sd_uhsii,8,4,4,2,very_high,215,450,440,steel,none,none,professional_keyboard,tpm_2_0
surface_studio_2_plus_2022,none,thunderbolt_4,2,1,true,sd,2,2,2,1,medium,615,200,470,aluminum,dual_array,quad_speaker,wireless_keyboard,tpm_2_0
modern_14_c13m,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
prestige_14_ai_studio_c1v,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,312,221,15,aluminum,quad_array,quad_speaker,backlit_chiclet,tpm_2_0
stealth_16_ai_studio_a1v,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
raider_18_hx_a14v,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
vector_16_hx_a14v,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
creator_z16_hx_studio_2023,none,thunderbolt_4,2,1,true,sd_uhsii,2,2,2,1,high,359,253,21,aluminum,dual_array,stereo,backlit_chiclet,tpm_2_0
predator_orion_5000_2025,none,none,0,3,true,none,4,2,3,1,very_high,220,450,470,steel_tempered_glass,none,none,mechanical_keyboard,tpm_2_0
precision_3680_tower_2024,none,thunderbolt_4,2,4,true,sd_uhsii,8,4,4,2,very_high,215,450,440,steel,none,none,professional_keyboard,tpm_2_0
alienware_aurora_r16,none,none,0,3,true,none,4,2,3,1,very_high,220,450,470,steel_tempered_glass,none,none,mechanical_keyboard,tpm_2_0
omen_35l_2024,none,none,0,3,true,none,4,2,3,1,very_high,220,450,470,steel_tempered_glass,none,none,mechanical_keyboard,tpm_2_0
inspiron_24_aio_5430,none,usb_c,0,1,true,sd,2,2,1,1,medium,540,190,420,aluminum_plastic,dual_array,stereo,wireless_keyboard,tpm_2_0
pavilion_24_aio_2024,none,usb_c,0,1,true,sd,2,2,1,1,medium,540,190,420,aluminum_plastic,dual_array,stereo,wireless_keyboard,tpm_2_0
poweredge_r760_2023,none,none,0,4,true,none,24,8,8,2,very_high,438,720,87,steel,none,none,none,tpm_2_0
poweredge_t560_2023,none,none,0,2,true,none,8,2,4,1,very_high,220,580,450,steel,none,none,none,tpm_2_0
proliant_dl380_gen11,none,none,0,4,true,none,24,8,8,2,very_high,438,720,87,steel,none,none,none,tpm_2_0
superserver_sys_221h_tnr_2023,none,none,0,4,true,none,24,8,8,2,very_high,438,720,87,steel,none,none,none,tpm_2_0
raspberry_pi_5_2023,none,none,0,2,true,microsd,0,0,1,0,medium,85,56,18,pcb,none,none,none,none
z2_tower_g9_2022,none,thunderbolt_4,2,4,true,sd_uhsii,8,4,4,2,very_high,215,450,440,steel,none,none,professional_keyboard,tpm_2_0
thinkpad_p14s_gen5,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
ideapad_slim_5_gen9,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
yoga_7_gen9,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,315,220,17,aluminum,dual_array,quad_speaker,backlit_chiclet,tpm_2_0
xps_13_9345,none,thunderbolt_4,2,0,false,none,0,0,1,1,low,304,215,15,aluminum,dual_array,stereo,backlit_chiclet,tpm_2_0
xps_16_9640,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,312,221,15,aluminum,quad_array,quad_speaker,backlit_chiclet,tpm_2_0
latitude_5450_2024,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
precision_5690_2024,none,thunderbolt_4,2,1,true,sd_uhsii,2,2,2,1,high,359,253,21,aluminum,dual_array,stereo,backlit_chiclet,tpm_2_0
inspiron_16_5640,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
alienware_m16_r2,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
elitebook_840_g11,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
probook_450_g11,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
zbook_firefly_14_g11,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
pavilion_15_2024,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
omen_16_2024,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
zenbook_14_ux3405,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,312,221,15,aluminum,quad_array,quad_speaker,backlit_chiclet,tpm_2_0
vivobook_16_x1605,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
rog_zephyrus_g14_ga403,none,thunderbolt_4,2,1,true,sd_uhsii,2,2,2,2,high,356,254,23,aluminum,dual_array,quad_speaker,backlit_gaming,tpm_2_0
tuf_gaming_a15_fa507,none,usb_c,0,1,true,sd,2,2,2,1,high,359,259,25,aluminum_plastic,dual_array,stereo,backlit_gaming,tpm_2_0
macbook_air_15_m4,none,thunderbolt,2,0,false,none,0,0,0,0,none,304,215,11,aluminum,triple_array,quad_speaker,backlit_chiclet,apple_secure_enclave
surface_laptop_13_first_edition,none,thunderbolt_4,2,0,false,none,0,0,1,1,low,304,215,15,aluminum,dual_array,stereo,backlit_chiclet,tpm_2_0
surface_pro_13_11th_edition,5g,usb_c,0,0,false,microsd,0,0,1,1,low,287,209,9,aluminum,dual_array,stereo,detachable_keyboard,tpm_2_0
framework_laptop_13_2025,5g,thunderbolt_4,2,0,false,nano_sim,0,0,1,1,low,305,218,15,magnesium_alloy,dual_array,stereo,backlit_chiclet,tpm_2_0
razer_blade_14_2025,none,thunderbolt_4,2,1,true,sd_uhsii,2,2,2,2,high,356,254,23,aluminum,dual_array,quad_speaker,backlit_gaming,tpm_2_0
galaxy_book5_pro_14_2025,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,312,221,15,aluminum,quad_array,quad_speaker,backlit_chiclet,tpm_2_0
thinkpad_t14_gen5,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
thinkpad_t14_gen6,none,thunderbolt_4,2,0,true,microsd,2,2,2,1,high,317,227,18,magnesium_alloy,dual_array,stereo,backlit_chiclet,tpm_2_0
thinkpad_x1_carbon_gen12,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,312,221,15,aluminum,quad_array,quad_speaker,backlit_chiclet,tpm_2_0
thinkpad_x1_carbon_gen13,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,312,221,15,aluminum,quad_array,quad_speaker,backlit_chiclet,tpm_2_0
legion_5_gen9,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
legion_5_gen10,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
macbook_air_m3,none,thunderbolt,2,0,false,none,0,0,0,0,none,304,215,11,aluminum,triple_array,quad_speaker,backlit_chiclet,apple_secure_enclave
macbook_air_m4,none,thunderbolt,2,0,false,none,0,0,0,0,none,304,215,11,aluminum,triple_array,quad_speaker,backlit_chiclet,apple_secure_enclave
macbook_pro_m4,none,thunderbolt,3,0,false,sdxc,0,0,0,0,none,313,221,16,aluminum,triple_array,six_speaker,backlit_chiclet,apple_secure_enclave
macbook_pro_m4_pro,none,thunderbolt,3,0,false,sdxc,0,0,0,0,none,313,221,16,aluminum,triple_array,six_speaker,backlit_chiclet,apple_secure_enclave
macbook_pro_m4_max,none,thunderbolt,3,0,false,sdxc,0,0,0,0,none,356,248,17,aluminum,triple_array,six_speaker,backlit_chiclet,apple_secure_enclave
optiplex_7020_2024,none,usb_c,0,2,true,sd,4,2,2,1,high,95,300,290,steel_plastic,none,internal_mono,external_keyboard,tpm_2_0
thinkcentre_m90s_gen5,none,usb_c,0,2,true,sd,4,2,2,1,high,95,300,290,steel_plastic,none,internal_mono,external_keyboard,tpm_2_0
asus_nuc_14_pro_2024,none,thunderbolt_4,2,2,true,none,2,2,2,1,high,117,112,54,aluminum_plastic,none,none,external_keyboard,tpm_2_0
zotac_zbox_magnus_en474070c,none,thunderbolt_4,2,3,true,sd,2,2,3,2,very_high,210,203,62,aluminum,none,none,external_keyboard,tpm_2_0
ultrabook_13_standard,none,thunderbolt_4,2,0,false,none,0,0,1,1,low,304,215,15,aluminum,dual_array,stereo,backlit_chiclet,tpm_2_0
ultrabook_13_business,5g,thunderbolt_4,2,0,false,nano_sim,0,0,1,1,low,305,218,15,magnesium_alloy,dual_array,stereo,backlit_chiclet,tpm_2_0
business_laptop_14_standard,none,usb_c,1,0,true,microsd,2,1,1,1,medium,317,227,18,aluminum_plastic,dual_array,stereo,backlit_chiclet,tpm_2_0
business_laptop_14_docked,none,thunderbolt_4,2,0,true,microsd,2,2,2,1,high,317,227,18,magnesium_alloy,dual_array,stereo,backlit_chiclet,tpm_2_0
business_laptop_14_cellular,5g,thunderbolt_4,2,0,true,nano_sim,2,2,2,1,high,317,227,18,magnesium_alloy,dual_array,stereo,backlit_chiclet,tpm_2_0
premium_laptop_14,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,312,221,15,aluminum,quad_array,quad_speaker,backlit_chiclet,tpm_2_0
convertible_laptop_14,none,thunderbolt_4,2,0,false,microsd,0,0,1,1,low,315,220,17,aluminum,dual_array,quad_speaker,backlit_chiclet,tpm_2_0
detachable_13,5g,usb_c,0,0,false,microsd,0,0,1,1,low,287,209,9,aluminum,dual_array,stereo,detachable_keyboard,tpm_2_0
gaming_laptop_15,none,usb_c,0,1,true,sd,2,2,2,1,high,359,259,25,aluminum_plastic,dual_array,stereo,backlit_gaming,tpm_2_0
gaming_laptop_16,none,usb_c,1,1,true,sd,2,2,2,2,high,360,260,26,aluminum_plastic,dual_array,quad_speaker,backlit_gaming,tpm_2_0
premium_gaming_laptop_16,none,thunderbolt_4,2,1,true,sd_uhsii,2,2,2,2,high,356,254,23,aluminum,dual_array,quad_speaker,backlit_gaming,tpm_2_0
mobile_workstation_16,none,thunderbolt_4,2,1,true,sd_uhsii,2,2,2,1,high,359,253,21,aluminum,dual_array,stereo,backlit_chiclet,tpm_2_0
macbook_air_13,none,thunderbolt,2,0,false,none,0,0,0,0,none,304,215,11,aluminum,triple_array,quad_speaker,backlit_chiclet,apple_secure_enclave
macbook_pro_14,none,thunderbolt,3,0,false,sdxc,0,0,0,0,none,313,221,16,aluminum,triple_array,six_speaker,backlit_chiclet,apple_secure_enclave
macbook_pro_16,none,thunderbolt,3,0,false,sdxc,0,0,0,0,none,356,248,17,aluminum,triple_array,six_speaker,backlit_chiclet,apple_secure_enclave
desktop_tower_consumer,none,none,0,1,true,sd,4,2,2,1,high,175,350,360,steel_plastic,none,none,external_keyboard,tpm_2_0
desktop_tower_gaming,none,none,0,3,true,none,4,2,3,1,very_high,220,450,470,steel_tempered_glass,none,none,mechanical_keyboard,tpm_2_0
desktop_workstation_tower,none,thunderbolt_4,2,4,true,sd_uhsii,8,4,4,2,very_high,215,450,440,steel,none,none,professional_keyboard,tpm_2_0
desktop_sff_business,none,usb_c,0,2,true,sd,4,2,2,1,high,95,300,290,steel_plastic,none,internal_mono,external_keyboard,tpm_2_0
desktop_micro_business,none,usb_c,0,2,true,none,2,2,2,1,medium,180,180,37,plastic_metal,none,internal_mono,external_keyboard,tpm_2_0
all_in_one_24,none,usb_c,0,1,true,sd,2,2,1,1,medium,540,190,420,aluminum_plastic,dual_array,stereo,wireless_keyboard,tpm_2_0
all_in_one_27,none,thunderbolt_4,2,1,true,sd,2,2,2,1,medium,615,200,470,aluminum,dual_array,quad_speaker,wireless_keyboard,tpm_2_0
mini_pc_standard,none,usb_c,0,2,true,none,2,1,2,1,high,120,120,45,aluminum_plastic,none,none,external_keyboard,tpm_2_0
mini_pc_business,none,thunderbolt_4,2,2,true,none,2,2,2,1,high,117,112,54,aluminum_plastic,none,none,external_keyboard,tpm_2_0
mini_pc_performance,none,thunderbolt_4,2,3,true,sd,2,2,3,2,very_high,210,203,62,aluminum,none,none,external_keyboard,tpm_2_0
single_board_computer,none,none,0,2,true,microsd,0,0,1,0,medium,85,56,18,pcb,none,none,none,none
server_tower,none,none,0,2,true,none,8,2,4,1,very_high,220,580,450,steel,none,none,none,tpm_2_0
server_rack_1u,none,none,0,2,true,none,16,4,4,2,very_high,438,700,44,steel,none,none,none,tpm_2_0
server_rack_2u,none,none,0,4,true,none,24,8,8,2,very_high,438,720,87,steel,none,none,none,tpm_2_0
server_blade,none,none,0,0,true,none,16,8,2,2,high,215,510,55,steel,none,none,none,tpm_2_0
```

---

### form_factor.csv

```csv
id,en,fr
clamshell,Clamshell,Portable classique
convertible_360,360° convertible,Convertible 360°
detachable,Detachable,Détachable
rugged,Rugged,Renforcé
tower,Tower,Tour
small_form_factor,Small Form Factor,Petit format
micro,Micro,Micro format
mini,Mini,Mini format
stick,Compute stick,PC clé
integrated_display,Integrated display,Écran intégré
rackmount,Rackmount,Montable en rack
blade,Blade,Lame serveur
board,Board,Carte seule
```

---

### generation_color.csv

```csv
generation_id,color_id,weight
aspire_5_a515_58m,silver,10
swift_go_14_sfg14_73,gray,10
travelmate_p4_14_tmp414_53,black,10
predator_helios_16_ph16_72,black,10
nitro_v_15_anv15_51,black,10
mac_mini_m4,silver,10
imac_24_m4,silver,10
mac_studio_m4_max,silver,10
mac_pro_m2_ultra,silver,10
expertbook_b5_b5404,black,10
proart_p16_h7606,gray,10
envy_16_2024,gray,10
victus_16_2024,black,10
thinkbook_14_gen7,black,10
loq_15_gen9,black,10
thinkstation_p3_tower_gen2,gray,10
surface_studio_2_plus_2022,silver,10
modern_14_c13m,silver,10
prestige_14_ai_studio_c1v,gray,10
stealth_16_ai_studio_a1v,black,10
raider_18_hx_a14v,black,10
vector_16_hx_a14v,black,10
creator_z16_hx_studio_2023,gray,10
predator_orion_5000_2025,black,10
precision_3680_tower_2024,gray,10
alienware_aurora_r16,black,10
omen_35l_2024,black,10
inspiron_24_aio_5430,white,10
pavilion_24_aio_2024,white,10
poweredge_r760_2023,gray,10
poweredge_t560_2023,gray,10
proliant_dl380_gen11,gray,10
superserver_sys_221h_tnr_2023,gray,10
raspberry_pi_5_2023,green,10
z2_tower_g9_2022,gray,10
thinkpad_p14s_gen5,black,10
ideapad_slim_5_gen9,silver,10
yoga_7_gen9,blue,10
xps_13_9345,silver,10
xps_16_9640,gray,10
latitude_5450_2024,black,10
precision_5690_2024,black,10
inspiron_16_5640,silver,10
alienware_m16_r2,black,10
elitebook_840_g11,black,10
probook_450_g11,silver,10
zbook_firefly_14_g11,black,10
pavilion_15_2024,silver,10
omen_16_2024,black,10
zenbook_14_ux3405,gray,10
vivobook_16_x1605,silver,10
rog_zephyrus_g14_ga403,black,10
tuf_gaming_a15_fa507,black,10
macbook_air_15_m4,silver,10
surface_laptop_13_first_edition,silver,10
surface_pro_13_11th_edition,silver,10
framework_laptop_13_2025,gray,10
razer_blade_14_2025,black,10
galaxy_book5_pro_14_2025,gray,10
thinkpad_t14_gen5,black,7
thinkpad_t14_gen5,gray,2
thinkpad_t14_gen5,silver,1
thinkpad_t14_gen6,black,7
thinkpad_t14_gen6,dark_gray,2
thinkpad_t14_gen6,silver,1
thinkpad_x1_carbon_gen12,black,9
thinkpad_x1_carbon_gen12,dark_gray,1
thinkpad_x1_carbon_gen13,black,9
thinkpad_x1_carbon_gen13,dark_gray,1
legion_5_gen9,black,7
legion_5_gen9,gray,2
legion_5_gen9,white,1
legion_5_gen10,black,6
legion_5_gen10,dark_gray,2
legion_5_gen10,white,2
macbook_air_m3,space_gray,3
macbook_air_m3,silver,3
macbook_air_m3,blue,2
macbook_air_m3,gold,2
macbook_air_m4,space_gray,3
macbook_air_m4,silver,3
macbook_air_m4,blue,3
macbook_air_m4,gold,1
macbook_pro_m4,space_gray,6
macbook_pro_m4,silver,4
macbook_pro_m4_pro,space_gray,7
macbook_pro_m4_pro,silver,3
macbook_pro_m4_max,space_gray,8
macbook_pro_m4_max,silver,2
optiplex_7020_2024,black,8
optiplex_7020_2024,dark_gray,2
thinkcentre_m90s_gen5,black,9
thinkcentre_m90s_gen5,dark_gray,1
asus_nuc_14_pro_2024,black,6
asus_nuc_14_pro_2024,dark_gray,4
zotac_zbox_magnus_en474070c,black,8
zotac_zbox_magnus_en474070c,dark_gray,2
```

---

### generation_cpu.csv

```csv
generation_id,cpu_id,weight
aspire_5_a515_58m,amd_ryzen_7_8840u,10
swift_go_14_sfg14_73,intel_core_ultra_7_258v,10
travelmate_p4_14_tmp414_53,intel_core_ultra_5_225u,10
predator_helios_16_ph16_72,amd_ryzen_ai_9_hx_370,10
nitro_v_15_anv15_51,amd_ryzen_ai_9_hx_370,10
mac_mini_m4,apple_m4,10
imac_24_m4,apple_m4,10
mac_studio_m4_max,apple_m4_max,10
mac_pro_m2_ultra,apple_m2_ultra,10
expertbook_b5_b5404,intel_core_ultra_5_225u,10
proart_p16_h7606,intel_core_ultra_9_285hx,10
envy_16_2024,intel_core_ultra_7_258v,10
victus_16_2024,amd_ryzen_ai_9_hx_370,10
thinkbook_14_gen7,intel_core_ultra_5_225u,10
loq_15_gen9,amd_ryzen_ai_9_hx_370,10
thinkstation_p3_tower_gen2,intel_core_ultra_9_285,10
surface_studio_2_plus_2022,intel_core_ultra_7_265,10
modern_14_c13m,intel_core_ultra_5_225u,10
prestige_14_ai_studio_c1v,intel_core_ultra_7_258v,10
stealth_16_ai_studio_a1v,amd_ryzen_ai_9_hx_370,10
raider_18_hx_a14v,amd_ryzen_ai_9_hx_370,10
vector_16_hx_a14v,amd_ryzen_ai_9_hx_370,10
creator_z16_hx_studio_2023,intel_core_ultra_9_285hx,10
predator_orion_5000_2025,intel_core_ultra_9_285,10
precision_3680_tower_2024,intel_core_ultra_9_285,10
alienware_aurora_r16,intel_core_ultra_9_285,10
omen_35l_2024,intel_core_ultra_9_285,10
inspiron_24_aio_5430,intel_core_ultra_5_245,10
pavilion_24_aio_2024,intel_core_ultra_5_245,10
poweredge_r760_2023,intel_xeon_silver_4510,10
poweredge_t560_2023,intel_xeon_silver_4510,10
proliant_dl380_gen11,intel_xeon_silver_4510,10
superserver_sys_221h_tnr_2023,intel_xeon_silver_4510,10
raspberry_pi_5_2023,broadcom_bcm2712,10
z2_tower_g9_2022,intel_core_ultra_9_285,10
thinkpad_p14s_gen5,intel_core_ultra_5_225u,10
ideapad_slim_5_gen9,amd_ryzen_7_8840u,10
yoga_7_gen9,intel_core_ultra_7_258v,10
xps_13_9345,intel_core_ultra_5_225u,10
xps_16_9640,intel_core_ultra_7_258v,10
latitude_5450_2024,intel_core_ultra_5_225u,10
precision_5690_2024,intel_core_ultra_9_285hx,10
inspiron_16_5640,amd_ryzen_7_8840u,10
alienware_m16_r2,amd_ryzen_ai_9_hx_370,10
elitebook_840_g11,intel_core_ultra_5_225u,10
probook_450_g11,amd_ryzen_7_8840u,10
zbook_firefly_14_g11,intel_core_ultra_5_225u,10
pavilion_15_2024,amd_ryzen_7_8840u,10
omen_16_2024,amd_ryzen_ai_9_hx_370,10
zenbook_14_ux3405,intel_core_ultra_7_258v,10
vivobook_16_x1605,amd_ryzen_7_8840u,10
rog_zephyrus_g14_ga403,amd_ryzen_ai_9_hx_370,10
tuf_gaming_a15_fa507,amd_ryzen_ai_9_hx_370,10
macbook_air_15_m4,apple_m4,10
surface_laptop_13_first_edition,intel_core_ultra_5_225u,10
surface_pro_13_11th_edition,intel_core_ultra_5_225u,10
framework_laptop_13_2025,intel_core_ultra_5_225u,10
razer_blade_14_2025,amd_ryzen_ai_9_hx_370,10
galaxy_book5_pro_14_2025,intel_core_ultra_7_258v,10
macbook_air_m3,apple_m3,10
macbook_air_m4,apple_m4,10
macbook_pro_m4,apple_m4,10
macbook_pro_m4_pro,apple_m4_pro,10
macbook_pro_m4_max,apple_m4_max,10
thinkpad_t14_gen5,intel_core_ultra_5_225u,5
thinkpad_t14_gen5,intel_core_ultra_7_258v,3
thinkpad_t14_gen5,amd_ryzen_7_8840u,2
thinkpad_t14_gen6,intel_core_ultra_5_225u,4
thinkpad_t14_gen6,intel_core_ultra_7_258v,4
thinkpad_t14_gen6,amd_ryzen_ai_7_350,2
thinkpad_x1_carbon_gen12,intel_core_ultra_5_225u,4
thinkpad_x1_carbon_gen12,intel_core_ultra_7_258v,6
thinkpad_x1_carbon_gen13,intel_core_ultra_5_225u,3
thinkpad_x1_carbon_gen13,intel_core_ultra_7_258v,7
legion_5_gen9,amd_ryzen_7_8840u,4
legion_5_gen9,amd_ryzen_9_9955hx,2
legion_5_gen9,intel_core_ultra_7_258v,3
legion_5_gen9,intel_core_ultra_9_285hx,1
legion_5_gen10,amd_ryzen_ai_7_350,3
legion_5_gen10,amd_ryzen_ai_9_hx_370,4
legion_5_gen10,intel_core_ultra_7_258v,2
legion_5_gen10,intel_core_ultra_9_285hx,1
optiplex_7020_2024,intel_core_ultra_5_245,6
optiplex_7020_2024,intel_core_ultra_7_265,3
optiplex_7020_2024,intel_core_ultra_9_285,1
thinkcentre_m90s_gen5,intel_core_ultra_5_245,5
thinkcentre_m90s_gen5,intel_core_ultra_7_265,4
thinkcentre_m90s_gen5,intel_core_ultra_9_285,1
asus_nuc_14_pro_2024,intel_core_ultra_5_225u,6
asus_nuc_14_pro_2024,intel_core_ultra_7_258v,4
zotac_zbox_magnus_en474070c,intel_core_ultra_7_258v,4
zotac_zbox_magnus_en474070c,intel_core_ultra_9_285hx,6
```

---

### generation_display.csv

```csv
generation_id,display_id,weight
aspire_5_a515_58m,ips_15_6_fhd_60,10
swift_go_14_sfg14_73,oled_14_2_8k_120,10
travelmate_p4_14_tmp414_53,ips_14_wuxga_60,10
predator_helios_16_ph16_72,ips_16_qhdplus_165,10
nitro_v_15_anv15_51,ips_15_6_fhd_165,10
mac_mini_m4,none,10
imac_24_m4,ips_24_fhd_75,10
mac_studio_m4_max,none,10
mac_pro_m2_ultra,none,10
expertbook_b5_b5404,ips_14_wuxga_60,10
proart_p16_h7606,ips_16_qhdplus_165,10
envy_16_2024,ips_16_wuxga_120,10
victus_16_2024,ips_16_qhdplus_165,10
thinkbook_14_gen7,ips_14_wuxga_60,10
loq_15_gen9,ips_15_6_fhd_165,10
thinkstation_p3_tower_gen2,none,10
surface_studio_2_plus_2022,ips_27_qhd_60,10
modern_14_c13m,ips_14_wuxga_60,10
prestige_14_ai_studio_c1v,oled_14_2_8k_120,10
stealth_16_ai_studio_a1v,ips_16_qhdplus_165,10
raider_18_hx_a14v,ips_16_qhdplus_165,10
vector_16_hx_a14v,ips_16_qhdplus_165,10
creator_z16_hx_studio_2023,ips_16_qhdplus_165,10
predator_orion_5000_2025,none,10
precision_3680_tower_2024,none,10
alienware_aurora_r16,none,10
omen_35l_2024,none,10
inspiron_24_aio_5430,ips_23_8_fhd_60,10
pavilion_24_aio_2024,ips_23_8_fhd_60,10
poweredge_r760_2023,none,10
poweredge_t560_2023,none,10
proliant_dl380_gen11,none,10
superserver_sys_221h_tnr_2023,none,10
raspberry_pi_5_2023,none,10
z2_tower_g9_2022,none,10
thinkpad_p14s_gen5,ips_14_wuxga_60,10
ideapad_slim_5_gen9,ips_16_wuxga_60,10
yoga_7_gen9,oled_14_2_8k_120_touch,10
xps_13_9345,ips_13_3_fhd_60,10
xps_16_9640,ips_16_wuxga_120,10
latitude_5450_2024,ips_14_wuxga_60,10
precision_5690_2024,ips_16_qhdplus_165,10
inspiron_16_5640,ips_16_wuxga_60,10
alienware_m16_r2,ips_16_qhdplus_165,10
elitebook_840_g11,ips_14_wuxga_60,10
probook_450_g11,ips_15_6_fhd_60,10
zbook_firefly_14_g11,ips_14_wuxga_60,10
pavilion_15_2024,ips_15_6_fhd_60,10
omen_16_2024,ips_16_qhdplus_165,10
zenbook_14_ux3405,oled_14_2_8k_120,10
vivobook_16_x1605,ips_16_wuxga_60,10
rog_zephyrus_g14_ga403,ips_14_qhdplus_120,10
tuf_gaming_a15_fa507,ips_15_6_fhd_165,10
macbook_air_15_m4,ips_15_3_2880_1864_60,10
surface_laptop_13_first_edition,ips_13_3_fhd_60,10
surface_pro_13_11th_edition,ips_13_3_fhd_60_touch,10
framework_laptop_13_2025,ips_13_3_fhd_60,10
razer_blade_14_2025,ips_14_qhdplus_120,10
galaxy_book5_pro_14_2025,oled_14_2_8k_120,10
thinkpad_t14_gen5,ips_14_wuxga_60,6
thinkpad_t14_gen5,ips_14_wuxga_60_touch,2
thinkpad_t14_gen5,oled_14_2_8k_120,2
thinkpad_t14_gen6,ips_14_wuxga_60,5
thinkpad_t14_gen6,ips_14_wuxga_60_touch,2
thinkpad_t14_gen6,ips_14_wuxga_120,2
thinkpad_t14_gen6,oled_14_2_8k_120,1
thinkpad_x1_carbon_gen12,ips_14_wuxga_60,4
thinkpad_x1_carbon_gen12,ips_14_wuxga_60_touch,2
thinkpad_x1_carbon_gen12,ips_14_qhdplus_120,2
thinkpad_x1_carbon_gen12,oled_14_2_8k_120,2
thinkpad_x1_carbon_gen13,ips_14_wuxga_60,3
thinkpad_x1_carbon_gen13,ips_14_wuxga_60_touch,2
thinkpad_x1_carbon_gen13,ips_14_qhdplus_120,2
thinkpad_x1_carbon_gen13,oled_14_2_8k_120,3
legion_5_gen9,ips_15_6_fhd_144,3
legion_5_gen9,ips_15_6_fhd_165,3
legion_5_gen9,ips_16_qhdplus_165,4
legion_5_gen10,ips_16_wuxga_120,2
legion_5_gen10,ips_16_qhdplus_165,5
legion_5_gen10,ips_16_qhdplus_240,2
legion_5_gen10,mini_led_16_qhdplus_240,1
macbook_air_m3,ips_13_6_2560_1664_60,10
macbook_air_m4,ips_13_6_2560_1664_60,10
macbook_pro_m4,ips_14_qhdplus_120,10
macbook_pro_m4_pro,ips_14_qhdplus_120,10
macbook_pro_m4_max,mini_led_16_qhdplus_240,10
optiplex_7020_2024,none,10
thinkcentre_m90s_gen5,none,10
asus_nuc_14_pro_2024,none,10
zotac_zbox_magnus_en474070c,none,10
```

---

### generation_gpu.csv

```csv
generation_id,gpu_id,weight
aspire_5_a515_58m,radeon_780m,10
swift_go_14_sfg14_73,arc_140v,10
travelmate_p4_14_tmp414_53,intel_integrated_graphics,10
predator_helios_16_ph16_72,rtx_5060_laptop,10
nitro_v_15_anv15_51,rtx_5060_laptop,10
mac_mini_m4,apple_m4_gpu,10
imac_24_m4,apple_m4_gpu,10
mac_studio_m4_max,apple_m4_max_gpu,10
mac_pro_m2_ultra,apple_m2_ultra_gpu,10
expertbook_b5_b5404,intel_integrated_graphics,10
proart_p16_h7606,rtx_5070_laptop,10
envy_16_2024,arc_140v,10
victus_16_2024,rtx_5060_laptop,10
thinkbook_14_gen7,intel_integrated_graphics,10
loq_15_gen9,rtx_5060_laptop,10
thinkstation_p3_tower_gen2,rtx_5070,10
surface_studio_2_plus_2022,intel_integrated_graphics,10
modern_14_c13m,intel_integrated_graphics,10
prestige_14_ai_studio_c1v,arc_140v,10
stealth_16_ai_studio_a1v,rtx_5060_laptop,10
raider_18_hx_a14v,rtx_5060_laptop,10
vector_16_hx_a14v,rtx_5060_laptop,10
creator_z16_hx_studio_2023,rtx_5070_laptop,10
predator_orion_5000_2025,rtx_5070,10
precision_3680_tower_2024,rtx_5070,10
alienware_aurora_r16,rtx_5070,10
omen_35l_2024,rtx_5070,10
inspiron_24_aio_5430,intel_integrated_graphics,10
pavilion_24_aio_2024,intel_integrated_graphics,10
poweredge_r760_2023,aspeed_ast2600,10
poweredge_t560_2023,aspeed_ast2600,10
proliant_dl380_gen11,aspeed_ast2600,10
superserver_sys_221h_tnr_2023,aspeed_ast2600,10
raspberry_pi_5_2023,videocore_vii,10
z2_tower_g9_2022,rtx_5070,10
thinkpad_p14s_gen5,intel_integrated_graphics,10
ideapad_slim_5_gen9,radeon_780m,10
yoga_7_gen9,arc_140v,10
xps_13_9345,intel_integrated_graphics,10
xps_16_9640,arc_140v,10
latitude_5450_2024,intel_integrated_graphics,10
precision_5690_2024,rtx_5070_laptop,10
inspiron_16_5640,radeon_780m,10
alienware_m16_r2,rtx_5060_laptop,10
elitebook_840_g11,intel_integrated_graphics,10
probook_450_g11,radeon_780m,10
zbook_firefly_14_g11,intel_integrated_graphics,10
pavilion_15_2024,radeon_780m,10
omen_16_2024,rtx_5060_laptop,10
zenbook_14_ux3405,arc_140v,10
vivobook_16_x1605,radeon_780m,10
rog_zephyrus_g14_ga403,rtx_5060_laptop,10
tuf_gaming_a15_fa507,rtx_5060_laptop,10
macbook_air_15_m4,apple_m4_gpu,10
surface_laptop_13_first_edition,intel_integrated_graphics,10
surface_pro_13_11th_edition,intel_integrated_graphics,10
framework_laptop_13_2025,intel_integrated_graphics,10
razer_blade_14_2025,rtx_5060_laptop,10
galaxy_book5_pro_14_2025,arc_140v,10
macbook_air_m3,apple_m3_gpu,10
macbook_air_m4,apple_m4_gpu,10
macbook_pro_m4,apple_m4_gpu,10
macbook_pro_m4_pro,apple_m4_pro_gpu,10
macbook_pro_m4_max,apple_m4_max_gpu,10
thinkpad_t14_gen5,intel_integrated_graphics,4
thinkpad_t14_gen5,arc_130v,2
thinkpad_t14_gen5,radeon_780m,3
thinkpad_t14_gen5,radeon_760m,1
thinkpad_t14_gen6,intel_integrated_graphics,2
thinkpad_t14_gen6,arc_130v,2
thinkpad_t14_gen6,arc_140v,3
thinkpad_t14_gen6,radeon_880m,1
thinkpad_t14_gen6,radeon_890m,2
thinkpad_x1_carbon_gen12,intel_integrated_graphics,7
thinkpad_x1_carbon_gen12,arc_130v,2
thinkpad_x1_carbon_gen12,arc_140v,1
thinkpad_x1_carbon_gen13,arc_130v,3
thinkpad_x1_carbon_gen13,arc_140v,7
legion_5_gen9,rtx_4060,1
legion_5_gen9,rtx_5050_laptop,1
legion_5_gen9,rtx_5060_laptop,3
legion_5_gen9,rtx_5070_laptop,3
legion_5_gen9,rtx_5070_ti_laptop,2
legion_5_gen10,rtx_5060_laptop,2
legion_5_gen10,rtx_5070_laptop,4
legion_5_gen10,rtx_5070_ti_laptop,3
legion_5_gen10,rtx_5080_laptop,1
optiplex_7020_2024,intel_integrated_graphics,7
optiplex_7020_2024,uhd_770,1
optiplex_7020_2024,arc_a380,2
thinkcentre_m90s_gen5,intel_integrated_graphics,7
thinkcentre_m90s_gen5,uhd_770,1
thinkcentre_m90s_gen5,arc_a380,2
asus_nuc_14_pro_2024,arc_130v,3
asus_nuc_14_pro_2024,arc_140v,7
zotac_zbox_magnus_en474070c,arc_140v,1
zotac_zbox_magnus_en474070c,rtx_5060_laptop,5
zotac_zbox_magnus_en474070c,rtx_5070_laptop,3
zotac_zbox_magnus_en474070c,rtx_5070_ti_laptop,1
```

---

### generation_memory.csv

```csv
generation_id,memory_id,weight
aspire_5_a515_58m,ddr5_16gb,10
swift_go_14_sfg14_73,lpddr5x_32gb,10
travelmate_p4_14_tmp414_53,ddr5_16gb,10
predator_helios_16_ph16_72,ddr5_32gb,10
nitro_v_15_anv15_51,ddr5_32gb,10
mac_mini_m4,unified_16gb,10
imac_24_m4,unified_16gb,10
mac_studio_m4_max,unified_48gb,10
mac_pro_m2_ultra,unified_64gb,10
expertbook_b5_b5404,ddr5_16gb,10
proart_p16_h7606,ddr5_32gb,10
envy_16_2024,lpddr5x_32gb,10
victus_16_2024,ddr5_32gb,10
thinkbook_14_gen7,ddr5_16gb,10
loq_15_gen9,ddr5_32gb,10
thinkstation_p3_tower_gen2,ddr5_32gb,10
surface_studio_2_plus_2022,ddr5_32gb,10
modern_14_c13m,ddr5_16gb,10
prestige_14_ai_studio_c1v,lpddr5x_32gb,10
stealth_16_ai_studio_a1v,ddr5_32gb,10
raider_18_hx_a14v,ddr5_32gb,10
vector_16_hx_a14v,ddr5_32gb,10
creator_z16_hx_studio_2023,ddr5_32gb,10
predator_orion_5000_2025,ddr5_32gb,10
precision_3680_tower_2024,ddr5_32gb,10
alienware_aurora_r16,ddr5_32gb,10
omen_35l_2024,ddr5_32gb,10
inspiron_24_aio_5430,ddr5_16gb,10
pavilion_24_aio_2024,ddr5_16gb,10
poweredge_r760_2023,ecc_ddr5_64gb,10
poweredge_t560_2023,ecc_ddr5_64gb,10
proliant_dl380_gen11,ecc_ddr5_64gb,10
superserver_sys_221h_tnr_2023,ecc_ddr5_64gb,10
raspberry_pi_5_2023,lpddr4x_8gb,10
z2_tower_g9_2022,ddr5_32gb,10
thinkpad_p14s_gen5,ddr5_16gb,10
ideapad_slim_5_gen9,ddr5_16gb,10
yoga_7_gen9,lpddr5x_32gb,10
xps_13_9345,ddr5_16gb,10
xps_16_9640,lpddr5x_32gb,10
latitude_5450_2024,ddr5_16gb,10
precision_5690_2024,ddr5_32gb,10
inspiron_16_5640,ddr5_16gb,10
alienware_m16_r2,ddr5_32gb,10
elitebook_840_g11,ddr5_16gb,10
probook_450_g11,ddr5_16gb,10
zbook_firefly_14_g11,ddr5_16gb,10
pavilion_15_2024,ddr5_16gb,10
omen_16_2024,ddr5_32gb,10
zenbook_14_ux3405,lpddr5x_32gb,10
vivobook_16_x1605,ddr5_16gb,10
rog_zephyrus_g14_ga403,ddr5_32gb,10
tuf_gaming_a15_fa507,ddr5_32gb,10
macbook_air_15_m4,unified_16gb,10
surface_laptop_13_first_edition,ddr5_16gb,10
surface_pro_13_11th_edition,ddr5_16gb,10
framework_laptop_13_2025,ddr5_16gb,10
razer_blade_14_2025,ddr5_32gb,10
galaxy_book5_pro_14_2025,lpddr5x_32gb,10
thinkpad_t14_gen5,ddr5_16gb,4
thinkpad_t14_gen5,ddr5_32gb,5
thinkpad_t14_gen5,ddr5_64gb,1
thinkpad_t14_gen6,ddr5_16gb,3
thinkpad_t14_gen6,ddr5_32gb,5
thinkpad_t14_gen6,ddr5_64gb,2
thinkpad_x1_carbon_gen12,lpddr5x_16gb,4
thinkpad_x1_carbon_gen12,lpddr5x_32gb,5
thinkpad_x1_carbon_gen12,lpddr5x_64gb,1
thinkpad_x1_carbon_gen13,lpddr5x_16gb,3
thinkpad_x1_carbon_gen13,lpddr5x_32gb,5
thinkpad_x1_carbon_gen13,lpddr5x_64gb,2
legion_5_gen9,ddr5_16gb,4
legion_5_gen9,ddr5_32gb,5
legion_5_gen9,ddr5_64gb,1
legion_5_gen10,ddr5_16gb,2
legion_5_gen10,ddr5_32gb,5
legion_5_gen10,ddr5_64gb,3
macbook_air_m3,unified_8gb,2
macbook_air_m3,unified_16gb,5
macbook_air_m3,unified_24gb,3
macbook_air_m4,unified_16gb,5
macbook_air_m4,unified_24gb,3
macbook_air_m4,unified_32gb,2
macbook_pro_m4,unified_16gb,4
macbook_pro_m4,unified_24gb,4
macbook_pro_m4,unified_32gb,2
macbook_pro_m4_pro,unified_24gb,3
macbook_pro_m4_pro,unified_48gb,5
macbook_pro_m4_pro,unified_64gb,2
macbook_pro_m4_max,unified_36gb,2
macbook_pro_m4_max,unified_48gb,3
macbook_pro_m4_max,unified_64gb,3
macbook_pro_m4_max,unified_128gb,2
optiplex_7020_2024,ddr5_16gb,5
optiplex_7020_2024,ddr5_32gb,4
optiplex_7020_2024,ddr5_64gb,1
thinkcentre_m90s_gen5,ddr5_16gb,4
thinkcentre_m90s_gen5,ddr5_32gb,5
thinkcentre_m90s_gen5,ddr5_64gb,1
asus_nuc_14_pro_2024,ddr5_16gb,4
asus_nuc_14_pro_2024,ddr5_32gb,5
asus_nuc_14_pro_2024,ddr5_64gb,1
zotac_zbox_magnus_en474070c,ddr5_32gb,5
zotac_zbox_magnus_en474070c,ddr5_64gb,4
zotac_zbox_magnus_en474070c,ddr5_96gb,1
```

---

### generation_operating_system.csv

```csv
generation_id,operating_system_id,weight
aspire_5_a515_58m,windows_11_home,10
swift_go_14_sfg14_73,windows_11_home,10
travelmate_p4_14_tmp414_53,windows_11_pro,10
predator_helios_16_ph16_72,windows_11_home,10
nitro_v_15_anv15_51,windows_11_home,10
mac_mini_m4,macos,10
imac_24_m4,macos,10
mac_studio_m4_max,macos,10
mac_pro_m2_ultra,macos,10
expertbook_b5_b5404,windows_11_pro,10
proart_p16_h7606,windows_11_pro_workstations,10
envy_16_2024,windows_11_home,10
victus_16_2024,windows_11_home,10
thinkbook_14_gen7,windows_11_pro,10
loq_15_gen9,windows_11_home,10
thinkstation_p3_tower_gen2,windows_11_pro_workstations,10
surface_studio_2_plus_2022,windows_11_pro,10
modern_14_c13m,windows_11_home,10
prestige_14_ai_studio_c1v,windows_11_home,10
stealth_16_ai_studio_a1v,windows_11_home,10
raider_18_hx_a14v,windows_11_home,10
vector_16_hx_a14v,windows_11_home,10
creator_z16_hx_studio_2023,windows_11_pro_workstations,10
predator_orion_5000_2025,windows_11_home,10
precision_3680_tower_2024,windows_11_pro_workstations,10
alienware_aurora_r16,windows_11_home,10
omen_35l_2024,windows_11_home,10
inspiron_24_aio_5430,windows_11_home,10
pavilion_24_aio_2024,windows_11_home,10
poweredge_r760_2023,ubuntu,10
poweredge_t560_2023,ubuntu,10
proliant_dl380_gen11,ubuntu,10
superserver_sys_221h_tnr_2023,ubuntu,10
raspberry_pi_5_2023,raspberry_pi_os,10
z2_tower_g9_2022,windows_11_pro_workstations,10
thinkpad_p14s_gen5,windows_11_pro,10
ideapad_slim_5_gen9,windows_11_home,10
yoga_7_gen9,windows_11_home,10
xps_13_9345,windows_11_home,10
xps_16_9640,windows_11_home,10
latitude_5450_2024,windows_11_pro,10
precision_5690_2024,windows_11_pro_workstations,10
inspiron_16_5640,windows_11_home,10
alienware_m16_r2,windows_11_home,10
elitebook_840_g11,windows_11_pro,10
probook_450_g11,windows_11_home,10
zbook_firefly_14_g11,windows_11_pro,10
pavilion_15_2024,windows_11_home,10
omen_16_2024,windows_11_home,10
zenbook_14_ux3405,windows_11_home,10
vivobook_16_x1605,windows_11_home,10
rog_zephyrus_g14_ga403,windows_11_home,10
tuf_gaming_a15_fa507,windows_11_home,10
macbook_air_15_m4,macos,10
surface_laptop_13_first_edition,windows_11_home,10
surface_pro_13_11th_edition,windows_11_pro,10
framework_laptop_13_2025,windows_11_pro,10
razer_blade_14_2025,windows_11_home,10
galaxy_book5_pro_14_2025,windows_11_home,10
thinkpad_t14_gen5,windows_11_pro,6
thinkpad_t14_gen5,windows_11_home,1
thinkpad_t14_gen5,ubuntu,2
thinkpad_t14_gen5,no_os,1
thinkpad_t14_gen6,windows_11_pro,7
thinkpad_t14_gen6,windows_11_home,1
thinkpad_t14_gen6,ubuntu,2
thinkpad_x1_carbon_gen12,windows_11_pro,8
thinkpad_x1_carbon_gen12,windows_11_home,1
thinkpad_x1_carbon_gen12,ubuntu,1
thinkpad_x1_carbon_gen13,windows_11_pro,8
thinkpad_x1_carbon_gen13,windows_11_home,1
thinkpad_x1_carbon_gen13,ubuntu,1
legion_5_gen9,windows_11_home,7
legion_5_gen9,windows_11_pro,2
legion_5_gen9,no_os,1
legion_5_gen10,windows_11_home,7
legion_5_gen10,windows_11_pro,2
legion_5_gen10,no_os,1
macbook_air_m3,macos,10
macbook_air_m4,macos,10
macbook_pro_m4,macos,10
macbook_pro_m4_pro,macos,10
macbook_pro_m4_max,macos,10
optiplex_7020_2024,windows_11_pro,7
optiplex_7020_2024,windows_11_home,1
optiplex_7020_2024,ubuntu,1
optiplex_7020_2024,no_os,1
thinkcentre_m90s_gen5,windows_11_pro,7
thinkcentre_m90s_gen5,windows_11_home,1
thinkcentre_m90s_gen5,ubuntu,1
thinkcentre_m90s_gen5,no_os,1
asus_nuc_14_pro_2024,windows_11_pro,5
asus_nuc_14_pro_2024,windows_11_home,2
asus_nuc_14_pro_2024,ubuntu,2
asus_nuc_14_pro_2024,no_os,1
zotac_zbox_magnus_en474070c,windows_11_home,6
zotac_zbox_magnus_en474070c,windows_11_pro,2
zotac_zbox_magnus_en474070c,ubuntu,1
zotac_zbox_magnus_en474070c,no_os,1
```

---

### generation_profile.csv

```csv
id,en,fr
balanced,Balanced catalogue,Catalogue équilibré
consumer,Consumer-focused catalogue,Catalogue orienté grand public
business,Business-focused catalogue,Catalogue orienté professionnel
gaming,Gaming-focused catalogue,Catalogue orienté jeu
creator,Creator-focused catalogue,Catalogue orienté création
workstation,Workstation-focused catalogue,Catalogue orienté station de travail
enterprise,Enterprise-focused catalogue,Catalogue orienté entreprise
mixed,Highly diversified catalogue,Catalogue très diversifié
portable_only,Portable computers only,Ordinateurs portables seulement
```

---

### generation_profile_computer_type.csv

```csv
generation_profile_id,computer_type_id,weight
balanced,laptop,8
balanced,desktop,5
balanced,all_in_one,2
balanced,mini_pc,3
balanced,single_board_computer,1
balanced,server,1
consumer,laptop,10
consumer,desktop,5
consumer,all_in_one,3
consumer,mini_pc,2
business,laptop,8
business,desktop,6
business,all_in_one,2
business,mini_pc,4
gaming,laptop,6
gaming,desktop,8
creator,laptop,6
creator,desktop,5
workstation,laptop,4
workstation,desktop,8
enterprise,laptop,3
enterprise,desktop,4
enterprise,mini_pc,3
enterprise,server,8
```

---

### generation_profile_segment.csv

```csv
generation_profile_id,product_segment_id,weight
balanced,consumer,5
balanced,business,5
balanced,premium,3
balanced,gaming,3
balanced,creator,2
balanced,workstation,2
balanced,enterprise,1
consumer,consumer,10
consumer,business,2
consumer,premium,4
consumer,gaming,3
business,business,10
business,premium,3
business,enterprise,3
gaming,gaming,10
gaming,consumer,2
gaming,premium,4
creator,creator,10
creator,premium,5
creator,workstation,3
workstation,workstation,10
workstation,business,3
workstation,enterprise,4
enterprise,enterprise,10
enterprise,business,4
enterprise,workstation,3
```

---

### generation_storage.csv

```csv
generation_id,storage_id,weight
aspire_5_a515_58m,nvme_ssd_512gb,10
swift_go_14_sfg14_73,nvme_ssd_1tb,10
travelmate_p4_14_tmp414_53,nvme_ssd_512gb,10
predator_helios_16_ph16_72,nvme_ssd_1tb,10
nitro_v_15_anv15_51,nvme_ssd_1tb,10
mac_mini_m4,nvme_ssd_512gb,10
imac_24_m4,nvme_ssd_512gb,10
mac_studio_m4_max,nvme_ssd_1tb,10
mac_pro_m2_ultra,nvme_ssd_1tb,10
expertbook_b5_b5404,nvme_ssd_512gb,10
proart_p16_h7606,nvme_ssd_1tb,10
envy_16_2024,nvme_ssd_1tb,10
victus_16_2024,nvme_ssd_1tb,10
thinkbook_14_gen7,nvme_ssd_512gb,10
loq_15_gen9,nvme_ssd_1tb,10
thinkstation_p3_tower_gen2,nvme_ssd_1tb,10
surface_studio_2_plus_2022,nvme_ssd_1tb,10
modern_14_c13m,nvme_ssd_512gb,10
prestige_14_ai_studio_c1v,nvme_ssd_1tb,10
stealth_16_ai_studio_a1v,nvme_ssd_1tb,10
raider_18_hx_a14v,nvme_ssd_1tb,10
vector_16_hx_a14v,nvme_ssd_1tb,10
creator_z16_hx_studio_2023,nvme_ssd_1tb,10
predator_orion_5000_2025,nvme_ssd_1tb,10
precision_3680_tower_2024,nvme_ssd_1tb,10
alienware_aurora_r16,nvme_ssd_1tb,10
omen_35l_2024,nvme_ssd_1tb,10
inspiron_24_aio_5430,nvme_ssd_512gb,10
pavilion_24_aio_2024,nvme_ssd_512gb,10
poweredge_r760_2023,nvme_ssd_1tb,10
poweredge_t560_2023,nvme_ssd_1tb,10
proliant_dl380_gen11,nvme_ssd_1tb,10
superserver_sys_221h_tnr_2023,nvme_ssd_1tb,10
raspberry_pi_5_2023,microsd_64gb,10
z2_tower_g9_2022,nvme_ssd_1tb,10
thinkpad_p14s_gen5,nvme_ssd_512gb,10
ideapad_slim_5_gen9,nvme_ssd_512gb,10
yoga_7_gen9,nvme_ssd_1tb,10
xps_13_9345,nvme_ssd_512gb,10
xps_16_9640,nvme_ssd_1tb,10
latitude_5450_2024,nvme_ssd_512gb,10
precision_5690_2024,nvme_ssd_1tb,10
inspiron_16_5640,nvme_ssd_512gb,10
alienware_m16_r2,nvme_ssd_1tb,10
elitebook_840_g11,nvme_ssd_512gb,10
probook_450_g11,nvme_ssd_512gb,10
zbook_firefly_14_g11,nvme_ssd_512gb,10
pavilion_15_2024,nvme_ssd_512gb,10
omen_16_2024,nvme_ssd_1tb,10
zenbook_14_ux3405,nvme_ssd_1tb,10
vivobook_16_x1605,nvme_ssd_512gb,10
rog_zephyrus_g14_ga403,nvme_ssd_1tb,10
tuf_gaming_a15_fa507,nvme_ssd_1tb,10
macbook_air_15_m4,nvme_ssd_512gb,10
surface_laptop_13_first_edition,nvme_ssd_512gb,10
surface_pro_13_11th_edition,nvme_ssd_512gb,10
framework_laptop_13_2025,nvme_ssd_512gb,10
razer_blade_14_2025,nvme_ssd_1tb,10
galaxy_book5_pro_14_2025,nvme_ssd_1tb,10
thinkpad_t14_gen5,nvme_ssd_256gb,1
thinkpad_t14_gen5,nvme_ssd_512gb,4
thinkpad_t14_gen5,nvme_ssd_1tb,4
thinkpad_t14_gen5,nvme_ssd_2tb,1
thinkpad_t14_gen6,nvme_ssd_512gb,3
thinkpad_t14_gen6,nvme_ssd_1tb,5
thinkpad_t14_gen6,nvme_ssd_2tb,2
thinkpad_x1_carbon_gen12,nvme_ssd_512gb,4
thinkpad_x1_carbon_gen12,nvme_ssd_1tb,5
thinkpad_x1_carbon_gen12,nvme_ssd_2tb,1
thinkpad_x1_carbon_gen13,nvme_ssd_512gb,3
thinkpad_x1_carbon_gen13,nvme_ssd_1tb,5
thinkpad_x1_carbon_gen13,nvme_ssd_2tb,2
legion_5_gen9,nvme_ssd_512gb,2
legion_5_gen9,nvme_ssd_1tb,5
legion_5_gen9,nvme_ssd_2tb,3
legion_5_gen10,nvme_ssd_1tb,5
legion_5_gen10,nvme_ssd_2tb,4
legion_5_gen10,nvme_ssd_4tb,1
macbook_air_m3,nvme_ssd_256gb,3
macbook_air_m3,nvme_ssd_512gb,4
macbook_air_m3,nvme_ssd_1tb,2
macbook_air_m3,nvme_ssd_2tb,1
macbook_air_m4,nvme_ssd_256gb,2
macbook_air_m4,nvme_ssd_512gb,4
macbook_air_m4,nvme_ssd_1tb,3
macbook_air_m4,nvme_ssd_2tb,1
macbook_pro_m4,nvme_ssd_512gb,4
macbook_pro_m4,nvme_ssd_1tb,4
macbook_pro_m4,nvme_ssd_2tb,2
macbook_pro_m4_pro,nvme_ssd_512gb,2
macbook_pro_m4_pro,nvme_ssd_1tb,4
macbook_pro_m4_pro,nvme_ssd_2tb,3
macbook_pro_m4_pro,nvme_ssd_4tb,1
macbook_pro_m4_max,nvme_ssd_1tb,3
macbook_pro_m4_max,nvme_ssd_2tb,4
macbook_pro_m4_max,nvme_ssd_4tb,2
macbook_pro_m4_max,nvme_ssd_8tb,1
optiplex_7020_2024,nvme_ssd_256gb,1
optiplex_7020_2024,nvme_ssd_512gb,4
optiplex_7020_2024,nvme_ssd_1tb,4
optiplex_7020_2024,nvme_ssd_2tb,1
optiplex_7020_2024,sata_ssd_512gb,2
optiplex_7020_2024,sata_ssd_1tb,1
thinkcentre_m90s_gen5,nvme_ssd_512gb,3
thinkcentre_m90s_gen5,nvme_ssd_1tb,5
thinkcentre_m90s_gen5,nvme_ssd_2tb,2
thinkcentre_m90s_gen5,sata_ssd_512gb,1
thinkcentre_m90s_gen5,sata_ssd_1tb,1
asus_nuc_14_pro_2024,nvme_ssd_256gb,1
asus_nuc_14_pro_2024,nvme_ssd_512gb,4
asus_nuc_14_pro_2024,nvme_ssd_1tb,4
asus_nuc_14_pro_2024,nvme_ssd_2tb,1
zotac_zbox_magnus_en474070c,nvme_ssd_512gb,1
zotac_zbox_magnus_en474070c,nvme_ssd_1tb,5
zotac_zbox_magnus_en474070c,nvme_ssd_2tb,3
zotac_zbox_magnus_en474070c,nvme_ssd_4tb,1
```

---

### gpu.csv

```csv
id,en,fr,brand_id,family,model,gpu_type,vram_gb
apple_m3_gpu,Apple M3 GPU,Apple M3 GPU,apple,apple_integrated,M3 GPU,integrated,0
apple_m4_gpu,Apple M4 GPU,Apple M4 GPU,apple,apple_integrated,M4 GPU,integrated,0
apple_m4_pro_gpu,Apple M4 Pro GPU,Apple M4 Pro GPU,apple,apple_integrated,M4 Pro GPU,integrated,0
apple_m4_max_gpu,Apple M4 Max GPU,Apple M4 Max GPU,apple,apple_integrated,M4 Max GPU,integrated,0
apple_m2_ultra_gpu,Apple M2 Ultra GPU,Apple M2 Ultra GPU,apple,apple_integrated,M2 Ultra GPU,integrated,0
aspeed_ast2600,ASPEED AST2600,ASPEED AST2600,aspeed,aspeed_ast,AST2600,integrated,0
videocore_vii,VideoCore VII,VideoCore VII,broadcom,videocore,VideoCore VII,integrated,0
rtx_5090,NVIDIA GeForce RTX 5090,NVIDIA GeForce RTX 5090,nvidia,nvidia_geforce_rtx_50,RTX 5090,dedicated,32
rtx_5080,NVIDIA GeForce RTX 5080,NVIDIA GeForce RTX 5080,nvidia,nvidia_geforce_rtx_50,RTX 5080,dedicated,16
rtx_5070_ti,NVIDIA GeForce RTX 5070 Ti,NVIDIA GeForce RTX 5070 Ti,nvidia,nvidia_geforce_rtx_50,RTX 5070 Ti,dedicated,16
rtx_5070,NVIDIA GeForce RTX 5070,NVIDIA GeForce RTX 5070,nvidia,nvidia_geforce_rtx_50,RTX 5070,dedicated,12
rtx_5060_ti_16gb,NVIDIA GeForce RTX 5060 Ti 16 GB,NVIDIA GeForce RTX 5060 Ti 16 Go,nvidia,nvidia_geforce_rtx_50,RTX 5060 Ti,dedicated,16
rtx_5060_ti_8gb,NVIDIA GeForce RTX 5060 Ti 8 GB,NVIDIA GeForce RTX 5060 Ti 8 Go,nvidia,nvidia_geforce_rtx_50,RTX 5060 Ti,dedicated,8
rtx_5060,NVIDIA GeForce RTX 5060,NVIDIA GeForce RTX 5060,nvidia,nvidia_geforce_rtx_50,RTX 5060,dedicated,8
rtx_5050,NVIDIA GeForce RTX 5050,NVIDIA GeForce RTX 5050,nvidia,nvidia_geforce_rtx_50,RTX 5050,dedicated,8
rtx_5090_laptop,NVIDIA GeForce RTX 5090 Laptop GPU,NVIDIA GeForce RTX 5090 pour portable,nvidia,nvidia_geforce_rtx_50,RTX 5090 Laptop GPU,dedicated,24
rtx_5080_laptop,NVIDIA GeForce RTX 5080 Laptop GPU,NVIDIA GeForce RTX 5080 pour portable,nvidia,nvidia_geforce_rtx_50,RTX 5080 Laptop GPU,dedicated,16
rtx_5070_ti_laptop,NVIDIA GeForce RTX 5070 Ti Laptop GPU,NVIDIA GeForce RTX 5070 Ti pour portable,nvidia,nvidia_geforce_rtx_50,RTX 5070 Ti Laptop GPU,dedicated,12
rtx_5070_laptop,NVIDIA GeForce RTX 5070 Laptop GPU,NVIDIA GeForce RTX 5070 pour portable,nvidia,nvidia_geforce_rtx_50,RTX 5070 Laptop GPU,dedicated,8
rtx_5060_laptop,NVIDIA GeForce RTX 5060 Laptop GPU,NVIDIA GeForce RTX 5060 pour portable,nvidia,nvidia_geforce_rtx_50,RTX 5060 Laptop GPU,dedicated,8
rtx_5050_laptop,NVIDIA GeForce RTX 5050 Laptop GPU,NVIDIA GeForce RTX 5050 pour portable,nvidia,nvidia_geforce_rtx_50,RTX 5050 Laptop GPU,dedicated,8
rtx_4090,NVIDIA GeForce RTX 4090,NVIDIA GeForce RTX 4090,nvidia,nvidia_geforce_rtx_40,RTX 4090,dedicated,24
rtx_4080,NVIDIA GeForce RTX 4080,NVIDIA GeForce RTX 4080,nvidia,nvidia_geforce_rtx_40,RTX 4080,dedicated,16
rtx_4070_ti,NVIDIA GeForce RTX 4070 Ti,NVIDIA GeForce RTX 4070 Ti,nvidia,nvidia_geforce_rtx_40,RTX 4070 Ti,dedicated,12
rtx_4070,NVIDIA GeForce RTX 4070,NVIDIA GeForce RTX 4070,nvidia,nvidia_geforce_rtx_40,RTX 4070,dedicated,12
rtx_4060_ti,NVIDIA GeForce RTX 4060 Ti,NVIDIA GeForce RTX 4060 Ti,nvidia,nvidia_geforce_rtx_40,RTX 4060 Ti,dedicated,8
rtx_4060,NVIDIA GeForce RTX 4060,NVIDIA GeForce RTX 4060,nvidia,nvidia_geforce_rtx_40,RTX 4060,dedicated,8
rtx_3060,NVIDIA GeForce RTX 3060,NVIDIA GeForce RTX 3060,nvidia,nvidia_geforce_rtx_30,RTX 3060,dedicated,12
rx_9070_xt,AMD Radeon RX 9070 XT,AMD Radeon RX 9070 XT,amd,amd_radeon_rx_9000,RX 9070 XT,dedicated,16
rx_9070,AMD Radeon RX 9070,AMD Radeon RX 9070,amd,amd_radeon_rx_9000,RX 9070,dedicated,16
rx_7900_xtx,AMD Radeon RX 7900 XTX,AMD Radeon RX 7900 XTX,amd,amd_radeon_rx_7000,RX 7900 XTX,dedicated,24
rx_7800_xt,AMD Radeon RX 7800 XT,AMD Radeon RX 7800 XT,amd,amd_radeon_rx_7000,RX 7800 XT,dedicated,16
rx_7700_xt,AMD Radeon RX 7700 XT,AMD Radeon RX 7700 XT,amd,amd_radeon_rx_7000,RX 7700 XT,dedicated,12
rx_7600,AMD Radeon RX 7600,AMD Radeon RX 7600,amd,amd_radeon_rx_7000,RX 7600,dedicated,8
radeon_890m,AMD Radeon 890M,AMD Radeon 890M,amd,amd_radeon_800m,Radeon 890M,integrated,0
radeon_880m,AMD Radeon 880M,AMD Radeon 880M,amd,amd_radeon_800m,Radeon 880M,integrated,0
radeon_780m,AMD Radeon 780M,AMD Radeon 780M,amd,amd_radeon_700m,Radeon 780M,integrated,0
radeon_760m,AMD Radeon 760M,AMD Radeon 760M,amd,amd_radeon_700m,Radeon 760M,integrated,0
arc_b580,Intel Arc B580,Intel Arc B580,intel,intel_arc_b,Arc B580,dedicated,12
arc_b570,Intel Arc B570,Intel Arc B570,intel,intel_arc_b,Arc B570,dedicated,10
arc_a770,Intel Arc A770,Intel Arc A770,intel,intel_arc_a,Arc A770,dedicated,16
arc_a750,Intel Arc A750,Intel Arc A750,intel,intel_arc_a,Arc A750,dedicated,8
arc_a380,Intel Arc A380,Intel Arc A380,intel,intel_arc_a,Arc A380,dedicated,6
arc_140v,Intel Arc 140V,Intel Arc 140V,intel,intel_arc_integrated,Arc 140V,integrated,0
arc_130v,Intel Arc 130V,Intel Arc 130V,intel,intel_arc_integrated,Arc 130V,integrated,0
intel_integrated_graphics,Intel Integrated Graphics,Graphismes intégrés Intel,intel,intel_arc_integrated,Integrated Graphics,integrated,0
uhd_770,Intel UHD Graphics 770,Intel UHD Graphics 770,intel,intel_uhd,UHD Graphics 770,integrated,0
```

---

### gpu_display.csv

```csv
gpu_id,display_id
intel_integrated_graphics,ips_13_3_fhd_60_touch
rtx_5060_laptop,ips_14_qhdplus_120
apple_m3_gpu,ips_13_6_2560_1664_60
apple_m4_gpu,ips_13_6_2560_1664_60
apple_m4_gpu,ips_15_3_2880_1864_60
apple_m4_gpu,ips_14_qhdplus_120
apple_m4_gpu,ips_24_fhd_75
apple_m4_gpu,none
apple_m4_pro_gpu,ips_14_qhdplus_120
apple_m4_max_gpu,mini_led_16_qhdplus_240
apple_m4_max_gpu,none
apple_m2_ultra_gpu,none
aspeed_ast2600,none
videocore_vii,none
rtx_5090,none
rtx_5090,ips_24_fhd_75
rtx_5090,ips_27_qhd_60
rtx_5090,ips_27_4k_60
rtx_5090,oled_27_qhd_240
rtx_5080,none
rtx_5080,ips_24_fhd_75
rtx_5080,ips_27_qhd_60
rtx_5080,ips_27_4k_60
rtx_5080,oled_27_qhd_240
rtx_5070_ti,none
rtx_5070_ti,ips_24_fhd_75
rtx_5070_ti,ips_27_qhd_60
rtx_5070_ti,ips_27_4k_60
rtx_5070_ti,oled_27_qhd_240
rtx_5070,none
rtx_5070,ips_24_fhd_75
rtx_5070,ips_27_qhd_60
rtx_5070,ips_27_4k_60
rtx_5070,oled_27_qhd_240
rtx_5060_ti_16gb,none
rtx_5060_ti_16gb,ips_24_fhd_75
rtx_5060_ti_16gb,ips_27_qhd_60
rtx_5060_ti_16gb,ips_27_4k_60
rtx_5060_ti_16gb,oled_27_qhd_240
rtx_5060_ti_8gb,none
rtx_5060_ti_8gb,ips_24_fhd_75
rtx_5060_ti_8gb,ips_27_qhd_60
rtx_5060_ti_8gb,ips_27_4k_60
rtx_5060,none
rtx_5060,ips_24_fhd_75
rtx_5060,ips_27_qhd_60
rtx_5060,ips_27_4k_60
rtx_5050,none
rtx_5050,ips_24_fhd_75
rtx_5050,ips_27_qhd_60
rtx_5090_laptop,none
rtx_5090_laptop,ips_16_qhdplus_240
rtx_5090_laptop,mini_led_16_qhdplus_240
rtx_5090_laptop,oled_16_3_2k_120
rtx_5090_laptop,ips_17_3_qhd_240
rtx_5080_laptop,none
rtx_5080_laptop,ips_16_qhdplus_165
rtx_5080_laptop,ips_16_qhdplus_240
rtx_5080_laptop,mini_led_16_qhdplus_240
rtx_5080_laptop,ips_17_3_qhd_240
rtx_5070_ti_laptop,none
rtx_5070_ti_laptop,ips_15_6_fhd_165
rtx_5070_ti_laptop,ips_16_qhdplus_165
rtx_5070_ti_laptop,ips_16_qhdplus_240
rtx_5070_ti_laptop,ips_17_3_qhd_240
rtx_5070_laptop,none
rtx_5070_laptop,ips_15_6_fhd_144
rtx_5070_laptop,ips_15_6_fhd_165
rtx_5070_laptop,ips_16_wuxga_120
rtx_5070_laptop,ips_16_qhdplus_165
rtx_5070_laptop,ips_16_qhdplus_240
rtx_5060_laptop,none
rtx_5060_laptop,ips_15_6_fhd_144
rtx_5060_laptop,ips_15_6_fhd_165
rtx_5060_laptop,ips_16_wuxga_120
rtx_5060_laptop,ips_16_qhdplus_165
rtx_5050_laptop,none
rtx_5050_laptop,ips_15_6_fhd_144
rtx_5050_laptop,ips_15_6_fhd_165
rtx_5050_laptop,ips_16_wuxga_120
rtx_4090,none
rtx_4090,ips_24_fhd_75
rtx_4090,ips_27_qhd_60
rtx_4090,ips_27_4k_60
rtx_4090,oled_27_qhd_240
rtx_4080,none
rtx_4080,ips_24_fhd_75
rtx_4080,ips_27_qhd_60
rtx_4080,ips_27_4k_60
rtx_4080,oled_27_qhd_240
rtx_4070_ti,none
rtx_4070_ti,ips_24_fhd_75
rtx_4070_ti,ips_27_qhd_60
rtx_4070_ti,ips_27_4k_60
rtx_4070_ti,oled_27_qhd_240
rtx_4070,none
rtx_4070,ips_24_fhd_75
rtx_4070,ips_27_qhd_60
rtx_4070,ips_27_4k_60
rtx_4060_ti,none
rtx_4060_ti,ips_24_fhd_75
rtx_4060_ti,ips_27_qhd_60
rtx_4060_ti,ips_27_4k_60
rtx_4060,none
rtx_4060,ips_24_fhd_75
rtx_4060,ips_27_qhd_60
rtx_3060,none
rtx_3060,ips_24_fhd_75
rtx_3060,ips_27_qhd_60
rx_9070_xt,none
rx_9070_xt,ips_24_fhd_75
rx_9070_xt,ips_27_qhd_60
rx_9070_xt,ips_27_4k_60
rx_9070_xt,oled_27_qhd_240
rx_9070,none
rx_9070,ips_24_fhd_75
rx_9070,ips_27_qhd_60
rx_9070,ips_27_4k_60
rx_9070,oled_27_qhd_240
rx_7900_xtx,none
rx_7900_xtx,ips_24_fhd_75
rx_7900_xtx,ips_27_qhd_60
rx_7900_xtx,ips_27_4k_60
rx_7900_xtx,oled_27_qhd_240
rx_7800_xt,none
rx_7800_xt,ips_24_fhd_75
rx_7800_xt,ips_27_qhd_60
rx_7800_xt,ips_27_4k_60
rx_7800_xt,oled_27_qhd_240
rx_7700_xt,none
rx_7700_xt,ips_24_fhd_75
rx_7700_xt,ips_27_qhd_60
rx_7700_xt,ips_27_4k_60
rx_7600,none
rx_7600,ips_24_fhd_75
rx_7600,ips_27_qhd_60
radeon_890m,none
radeon_890m,ips_14_wuxga_60
radeon_890m,ips_14_wuxga_120
radeon_890m,oled_14_2_8k_120
radeon_890m,ips_15_6_fhd_60
radeon_890m,ips_16_wuxga_60
radeon_890m,ips_16_wuxga_120
radeon_890m,oled_16_3_2k_120
radeon_880m,none
radeon_880m,ips_14_wuxga_60
radeon_880m,ips_14_wuxga_120
radeon_880m,oled_14_2_8k_90
radeon_880m,ips_15_6_fhd_60
radeon_880m,ips_16_wuxga_60
radeon_880m,ips_16_wuxga_120
radeon_780m,none
radeon_780m,ips_13_3_fhd_60
radeon_780m,ips_14_wuxga_60
radeon_780m,ips_15_6_fhd_60
radeon_780m,ips_16_wuxga_60
radeon_760m,none
radeon_760m,ips_13_3_fhd_60
radeon_760m,ips_14_wuxga_60
radeon_760m,ips_15_6_fhd_60
radeon_760m,ips_16_wuxga_60
arc_b580,none
arc_b580,ips_24_fhd_75
arc_b580,ips_27_qhd_60
arc_b580,ips_27_4k_60
arc_b570,none
arc_b570,ips_24_fhd_75
arc_b570,ips_27_qhd_60
arc_b570,ips_27_4k_60
arc_a770,none
arc_a770,ips_24_fhd_75
arc_a770,ips_27_qhd_60
arc_a770,ips_27_4k_60
arc_a750,none
arc_a750,ips_24_fhd_75
arc_a750,ips_27_qhd_60
arc_a750,ips_27_4k_60
arc_a380,none
arc_a380,ips_24_fhd_75
arc_a380,ips_27_qhd_60
arc_140v,none
arc_140v,ips_13_3_fhd_60
arc_140v,ips_14_wuxga_60
arc_140v,ips_14_wuxga_120
arc_140v,ips_14_qhdplus_120
arc_140v,oled_14_2_8k_90
arc_140v,oled_14_2_8k_120
arc_140v,oled_14_2_8k_120_touch
arc_140v,ips_16_wuxga_60
arc_140v,ips_16_wuxga_120
arc_130v,none
arc_130v,ips_13_3_fhd_60
arc_130v,ips_14_wuxga_60
arc_130v,ips_14_wuxga_120
arc_130v,ips_15_6_fhd_60
arc_130v,ips_16_wuxga_60
intel_integrated_graphics,none
intel_integrated_graphics,ips_13_3_fhd_60
intel_integrated_graphics,ips_14_wuxga_60
intel_integrated_graphics,ips_15_6_fhd_60
intel_integrated_graphics,ips_16_wuxga_60
intel_integrated_graphics,ips_21_5_fhd_60
intel_integrated_graphics,ips_23_8_fhd_60
intel_integrated_graphics,ips_24_fhd_75
intel_integrated_graphics,ips_27_qhd_60
uhd_770,none
uhd_770,ips_21_5_fhd_60
uhd_770,ips_23_8_fhd_60
uhd_770,ips_24_fhd_75
uhd_770,ips_27_qhd_60
uhd_770,ips_27_4k_60
```

---

### gpu_memory_weight.csv

```csv
gpu_id,memory_id,weight
rtx_5090,ddr5_32gb,2
rtx_5090,ddr5_48gb,3
rtx_5090,ddr5_64gb,6
rtx_5090,ddr5_96gb,5
rtx_5090,ddr5_128gb,3
rtx_5080,ddr5_32gb,3
rtx_5080,ddr5_48gb,4
rtx_5080,ddr5_64gb,6
rtx_5080,ddr5_96gb,3
rtx_5080,ddr5_128gb,1
rtx_5070_ti,ddr5_16gb,1
rtx_5070_ti,ddr5_32gb,5
rtx_5070_ti,ddr5_48gb,4
rtx_5070_ti,ddr5_64gb,5
rtx_5070_ti,ddr5_96gb,2
rtx_5070,ddr5_16gb,2
rtx_5070,ddr5_32gb,6
rtx_5070,ddr5_48gb,3
rtx_5070,ddr5_64gb,4
rtx_5070,ddr5_96gb,1
rtx_5060_ti_16gb,ddr5_16gb,3
rtx_5060_ti_16gb,ddr5_32gb,6
rtx_5060_ti_16gb,ddr5_48gb,3
rtx_5060_ti_16gb,ddr5_64gb,3
rtx_5060_ti_8gb,ddr5_16gb,4
rtx_5060_ti_8gb,ddr5_32gb,6
rtx_5060_ti_8gb,ddr5_48gb,2
rtx_5060_ti_8gb,ddr5_64gb,2
rtx_5060,ddr5_16gb,5
rtx_5060,ddr5_32gb,6
rtx_5060,ddr5_48gb,2
rtx_5060,ddr5_64gb,2
rtx_5050,ddr5_16gb,6
rtx_5050,ddr5_32gb,5
rtx_5050,ddr5_48gb,1
rtx_5050,ddr5_64gb,1
rtx_5090_laptop,ddr5_32gb,3
rtx_5090_laptop,ddr5_48gb,4
rtx_5090_laptop,ddr5_64gb,6
rtx_5090_laptop,ddr5_96gb,4
rtx_5090_laptop,lpddr5x_32gb,3
rtx_5090_laptop,lpddr5x_64gb,6
rtx_5080_laptop,ddr5_32gb,4
rtx_5080_laptop,ddr5_48gb,4
rtx_5080_laptop,ddr5_64gb,6
rtx_5080_laptop,ddr5_96gb,2
rtx_5080_laptop,lpddr5x_32gb,4
rtx_5080_laptop,lpddr5x_64gb,6
rtx_5070_ti_laptop,ddr5_16gb,1
rtx_5070_ti_laptop,ddr5_32gb,6
rtx_5070_ti_laptop,ddr5_48gb,4
rtx_5070_ti_laptop,ddr5_64gb,5
rtx_5070_ti_laptop,lpddr5x_32gb,6
rtx_5070_ti_laptop,lpddr5x_64gb,4
rtx_5070_laptop,ddr5_16gb,2
rtx_5070_laptop,ddr5_32gb,6
rtx_5070_laptop,ddr5_48gb,3
rtx_5070_laptop,ddr5_64gb,4
rtx_5070_laptop,lpddr5x_16gb,2
rtx_5070_laptop,lpddr5x_32gb,6
rtx_5070_laptop,lpddr5x_64gb,4
rtx_5060_laptop,ddr5_16gb,4
rtx_5060_laptop,ddr5_32gb,6
rtx_5060_laptop,ddr5_48gb,2
rtx_5060_laptop,ddr5_64gb,3
rtx_5060_laptop,lpddr5x_16gb,4
rtx_5060_laptop,lpddr5x_32gb,6
rtx_5060_laptop,lpddr5x_64gb,2
rtx_5050_laptop,ddr5_16gb,6
rtx_5050_laptop,ddr5_32gb,5
rtx_5050_laptop,ddr5_48gb,1
rtx_5050_laptop,ddr5_64gb,1
rtx_5050_laptop,lpddr5x_16gb,6
rtx_5050_laptop,lpddr5x_32gb,5
rtx_4090,ddr5_32gb,3
rtx_4090,ddr5_48gb,4
rtx_4090,ddr5_64gb,6
rtx_4090,ddr5_96gb,4
rtx_4090,ddr5_128gb,2
rtx_4080,ddr5_32gb,4
rtx_4080,ddr5_48gb,4
rtx_4080,ddr5_64gb,6
rtx_4080,ddr5_96gb,3
rtx_4070_ti,ddr5_16gb,1
rtx_4070_ti,ddr5_32gb,6
rtx_4070_ti,ddr5_48gb,3
rtx_4070_ti,ddr5_64gb,5
rtx_4070,ddr5_16gb,2
rtx_4070,ddr5_32gb,6
rtx_4070,ddr5_48gb,3
rtx_4070,ddr5_64gb,4
rtx_4060_ti,ddr5_16gb,4
rtx_4060_ti,ddr5_32gb,6
rtx_4060_ti,ddr5_48gb,2
rtx_4060_ti,ddr5_64gb,2
rtx_4060,ddr5_16gb,5
rtx_4060,ddr5_32gb,6
rtx_4060,ddr5_48gb,2
rtx_4060,ddr5_64gb,1
rtx_3060,ddr4_16gb,5
rtx_3060,ddr4_32gb,6
rtx_3060,ddr4_64gb,2
rtx_3060,ddr5_16gb,5
rtx_3060,ddr5_32gb,6
rx_9070_xt,ddr5_32gb,4
rx_9070_xt,ddr5_48gb,4
rx_9070_xt,ddr5_64gb,6
rx_9070_xt,ddr5_96gb,3
rx_9070,ddr5_32gb,5
rx_9070,ddr5_48gb,3
rx_9070,ddr5_64gb,6
rx_9070,ddr5_96gb,2
rx_7900_xtx,ddr5_32gb,4
rx_7900_xtx,ddr5_48gb,4
rx_7900_xtx,ddr5_64gb,6
rx_7900_xtx,ddr5_96gb,3
rx_7900_xtx,ddr5_128gb,1
rx_7800_xt,ddr5_16gb,1
rx_7800_xt,ddr5_32gb,6
rx_7800_xt,ddr5_48gb,3
rx_7800_xt,ddr5_64gb,5
rx_7700_xt,ddr5_16gb,2
rx_7700_xt,ddr5_32gb,6
rx_7700_xt,ddr5_48gb,3
rx_7700_xt,ddr5_64gb,4
rx_7600,ddr5_16gb,5
rx_7600,ddr5_32gb,6
rx_7600,ddr5_48gb,2
rx_7600,ddr5_64gb,1
radeon_890m,ddr5_16gb,2
radeon_890m,ddr5_32gb,6
radeon_890m,ddr5_48gb,3
radeon_890m,ddr5_64gb,4
radeon_890m,lpddr5x_16gb,2
radeon_890m,lpddr5x_24gb,3
radeon_890m,lpddr5x_32gb,6
radeon_890m,lpddr5x_64gb,4
radeon_880m,ddr5_16gb,3
radeon_880m,ddr5_32gb,6
radeon_880m,ddr5_48gb,3
radeon_880m,ddr5_64gb,3
radeon_880m,lpddr5x_16gb,3
radeon_880m,lpddr5x_24gb,3
radeon_880m,lpddr5x_32gb,6
radeon_880m,lpddr5x_64gb,3
radeon_780m,ddr5_16gb,4
radeon_780m,ddr5_32gb,6
radeon_780m,ddr5_64gb,2
radeon_780m,lpddr5x_16gb,4
radeon_780m,lpddr5x_24gb,3
radeon_780m,lpddr5x_32gb,6
radeon_780m,lpddr5x_64gb,2
radeon_760m,ddr5_8gb,1
radeon_760m,ddr5_16gb,6
radeon_760m,ddr5_32gb,5
radeon_760m,ddr5_64gb,1
radeon_760m,lpddr5x_16gb,6
radeon_760m,lpddr5x_24gb,3
radeon_760m,lpddr5x_32gb,5
arc_b580,ddr5_16gb,2
arc_b580,ddr5_32gb,6
arc_b580,ddr5_48gb,3
arc_b580,ddr5_64gb,4
arc_b570,ddr5_16gb,3
arc_b570,ddr5_32gb,6
arc_b570,ddr5_48gb,2
arc_b570,ddr5_64gb,3
arc_a770,ddr4_16gb,2
arc_a770,ddr4_32gb,6
arc_a770,ddr4_64gb,3
arc_a770,ddr5_16gb,2
arc_a770,ddr5_32gb,6
arc_a770,ddr5_64gb,4
arc_a750,ddr4_16gb,3
arc_a750,ddr4_32gb,6
arc_a750,ddr4_64gb,2
arc_a750,ddr5_16gb,3
arc_a750,ddr5_32gb,6
arc_a750,ddr5_64gb,3
arc_a380,ddr4_8gb,1
arc_a380,ddr4_16gb,6
arc_a380,ddr4_32gb,5
arc_a380,ddr5_16gb,6
arc_a380,ddr5_32gb,5
arc_a380,ddr5_64gb,1
arc_140v,ddr5_16gb,3
arc_140v,ddr5_32gb,6
arc_140v,ddr5_64gb,3
arc_140v,lpddr5x_16gb,3
arc_140v,lpddr5x_24gb,4
arc_140v,lpddr5x_32gb,6
arc_140v,lpddr5x_64gb,3
arc_130v,ddr5_16gb,5
arc_130v,ddr5_32gb,6
arc_130v,ddr5_64gb,2
arc_130v,lpddr5x_16gb,5
arc_130v,lpddr5x_24gb,3
arc_130v,lpddr5x_32gb,6
arc_130v,lpddr5x_64gb,2
intel_integrated_graphics,ddr4_8gb,2
intel_integrated_graphics,ddr4_16gb,6
intel_integrated_graphics,ddr4_32gb,5
intel_integrated_graphics,ddr4_64gb,2
intel_integrated_graphics,ddr5_8gb,2
intel_integrated_graphics,ddr5_16gb,6
intel_integrated_graphics,ddr5_24gb,3
intel_integrated_graphics,ddr5_32gb,6
intel_integrated_graphics,ddr5_48gb,2
intel_integrated_graphics,ddr5_64gb,2
intel_integrated_graphics,lpddr5x_16gb,6
intel_integrated_graphics,lpddr5x_24gb,3
intel_integrated_graphics,lpddr5x_32gb,6
intel_integrated_graphics,lpddr5x_64gb,2
uhd_770,ddr4_8gb,1
uhd_770,ddr4_16gb,6
uhd_770,ddr4_32gb,5
uhd_770,ddr4_64gb,2
uhd_770,ddr5_8gb,1
uhd_770,ddr5_16gb,6
uhd_770,ddr5_32gb,5
uhd_770,ddr5_64gb,2
```

---

### gpu_storage_weight.csv

```csv
gpu_id,storage_id,weight
rtx_5090,nvme_ssd_1tb,2
rtx_5090,nvme_ssd_2tb,5
rtx_5090,nvme_ssd_4tb,6
rtx_5090,nvme_ssd_8tb,3
rtx_5080,nvme_ssd_1tb,3
rtx_5080,nvme_ssd_2tb,6
rtx_5080,nvme_ssd_4tb,5
rtx_5080,nvme_ssd_8tb,2
rtx_5070_ti,nvme_ssd_1tb,4
rtx_5070_ti,nvme_ssd_2tb,6
rtx_5070_ti,nvme_ssd_4tb,3
rtx_5070,nvme_ssd_512gb,1
rtx_5070,nvme_ssd_1tb,5
rtx_5070,nvme_ssd_2tb,6
rtx_5070,nvme_ssd_4tb,2
rtx_5060_ti_16gb,nvme_ssd_512gb,2
rtx_5060_ti_16gb,nvme_ssd_1tb,6
rtx_5060_ti_16gb,nvme_ssd_2tb,5
rtx_5060_ti_16gb,nvme_ssd_4tb,1
rtx_5060_ti_8gb,nvme_ssd_512gb,3
rtx_5060_ti_8gb,nvme_ssd_1tb,6
rtx_5060_ti_8gb,nvme_ssd_2tb,4
rtx_5060,nvme_ssd_512gb,4
rtx_5060,nvme_ssd_1tb,6
rtx_5060,nvme_ssd_2tb,3
rtx_5050,nvme_ssd_512gb,5
rtx_5050,nvme_ssd_1tb,6
rtx_5050,nvme_ssd_2tb,2
rtx_5090_laptop,nvme_ssd_1tb,3
rtx_5090_laptop,nvme_ssd_2tb,6
rtx_5090_laptop,nvme_ssd_4tb,4
rtx_5080_laptop,nvme_ssd_1tb,4
rtx_5080_laptop,nvme_ssd_2tb,6
rtx_5080_laptop,nvme_ssd_4tb,3
rtx_5070_ti_laptop,nvme_ssd_512gb,1
rtx_5070_ti_laptop,nvme_ssd_1tb,5
rtx_5070_ti_laptop,nvme_ssd_2tb,6
rtx_5070_ti_laptop,nvme_ssd_4tb,2
rtx_5070_laptop,nvme_ssd_512gb,2
rtx_5070_laptop,nvme_ssd_1tb,6
rtx_5070_laptop,nvme_ssd_2tb,5
rtx_5070_laptop,nvme_ssd_4tb,1
rtx_5060_laptop,nvme_ssd_512gb,3
rtx_5060_laptop,nvme_ssd_1tb,6
rtx_5060_laptop,nvme_ssd_2tb,4
rtx_5050_laptop,nvme_ssd_512gb,5
rtx_5050_laptop,nvme_ssd_1tb,6
rtx_5050_laptop,nvme_ssd_2tb,2
rtx_4090,nvme_ssd_1tb,3
rtx_4090,nvme_ssd_2tb,6
rtx_4090,nvme_ssd_4tb,5
rtx_4090,nvme_ssd_8tb,2
rtx_4080,nvme_ssd_1tb,4
rtx_4080,nvme_ssd_2tb,6
rtx_4080,nvme_ssd_4tb,4
rtx_4070_ti,nvme_ssd_512gb,1
rtx_4070_ti,nvme_ssd_1tb,5
rtx_4070_ti,nvme_ssd_2tb,6
rtx_4070_ti,nvme_ssd_4tb,2
rtx_4070,nvme_ssd_512gb,2
rtx_4070,nvme_ssd_1tb,6
rtx_4070,nvme_ssd_2tb,5
rtx_4060_ti,nvme_ssd_512gb,3
rtx_4060_ti,nvme_ssd_1tb,6
rtx_4060_ti,nvme_ssd_2tb,4
rtx_4060,nvme_ssd_512gb,4
rtx_4060,nvme_ssd_1tb,6
rtx_4060,nvme_ssd_2tb,3
rtx_3060,sata_ssd_512gb,2
rtx_3060,sata_ssd_1tb,3
rtx_3060,nvme_ssd_512gb,4
rtx_3060,nvme_ssd_1tb,6
rtx_3060,nvme_ssd_2tb,3
rx_9070_xt,nvme_ssd_1tb,3
rx_9070_xt,nvme_ssd_2tb,6
rx_9070_xt,nvme_ssd_4tb,5
rx_9070_xt,nvme_ssd_8tb,1
rx_9070,nvme_ssd_1tb,4
rx_9070,nvme_ssd_2tb,6
rx_9070,nvme_ssd_4tb,4
rx_7900_xtx,nvme_ssd_1tb,3
rx_7900_xtx,nvme_ssd_2tb,6
rx_7900_xtx,nvme_ssd_4tb,5
rx_7900_xtx,nvme_ssd_8tb,2
rx_7800_xt,nvme_ssd_512gb,1
rx_7800_xt,nvme_ssd_1tb,5
rx_7800_xt,nvme_ssd_2tb,6
rx_7800_xt,nvme_ssd_4tb,2
rx_7700_xt,nvme_ssd_512gb,2
rx_7700_xt,nvme_ssd_1tb,6
rx_7700_xt,nvme_ssd_2tb,5
rx_7600,nvme_ssd_512gb,4
rx_7600,nvme_ssd_1tb,6
rx_7600,nvme_ssd_2tb,3
radeon_890m,nvme_ssd_256gb,1
radeon_890m,nvme_ssd_512gb,4
radeon_890m,nvme_ssd_1tb,6
radeon_890m,nvme_ssd_2tb,3
radeon_880m,nvme_ssd_256gb,1
radeon_880m,nvme_ssd_512gb,5
radeon_880m,nvme_ssd_1tb,6
radeon_880m,nvme_ssd_2tb,2
radeon_780m,nvme_ssd_256gb,2
radeon_780m,nvme_ssd_512gb,6
radeon_780m,nvme_ssd_1tb,5
radeon_780m,nvme_ssd_2tb,2
radeon_760m,nvme_ssd_256gb,3
radeon_760m,nvme_ssd_512gb,6
radeon_760m,nvme_ssd_1tb,4
arc_b580,nvme_ssd_512gb,2
arc_b580,nvme_ssd_1tb,6
arc_b580,nvme_ssd_2tb,5
arc_b580,nvme_ssd_4tb,2
arc_b570,nvme_ssd_512gb,3
arc_b570,nvme_ssd_1tb,6
arc_b570,nvme_ssd_2tb,4
arc_a770,nvme_ssd_512gb,2
arc_a770,nvme_ssd_1tb,6
arc_a770,nvme_ssd_2tb,5
arc_a770,nvme_ssd_4tb,2
arc_a750,nvme_ssd_512gb,3
arc_a750,nvme_ssd_1tb,6
arc_a750,nvme_ssd_2tb,4
arc_a380,sata_ssd_256gb,1
arc_a380,sata_ssd_512gb,3
arc_a380,sata_ssd_1tb,2
arc_a380,nvme_ssd_256gb,2
arc_a380,nvme_ssd_512gb,6
arc_a380,nvme_ssd_1tb,5
arc_a380,nvme_ssd_2tb,1
arc_140v,nvme_ssd_256gb,1
arc_140v,nvme_ssd_512gb,5
arc_140v,nvme_ssd_1tb,6
arc_140v,nvme_ssd_2tb,3
arc_140v,nvme_ssd_4tb,1
arc_130v,nvme_ssd_256gb,2
arc_130v,nvme_ssd_512gb,6
arc_130v,nvme_ssd_1tb,5
arc_130v,nvme_ssd_2tb,2
intel_integrated_graphics,sata_ssd_128gb,1
intel_integrated_graphics,sata_ssd_256gb,2
intel_integrated_graphics,sata_ssd_512gb,4
intel_integrated_graphics,sata_ssd_1tb,3
intel_integrated_graphics,nvme_ssd_128gb,1
intel_integrated_graphics,nvme_ssd_256gb,3
intel_integrated_graphics,nvme_ssd_512gb,6
intel_integrated_graphics,nvme_ssd_1tb,5
intel_integrated_graphics,nvme_ssd_2tb,2
uhd_770,sata_ssd_256gb,2
uhd_770,sata_ssd_512gb,4
uhd_770,sata_ssd_1tb,3
uhd_770,nvme_ssd_256gb,2
uhd_770,nvme_ssd_512gb,6
uhd_770,nvme_ssd_1tb,5
uhd_770,nvme_ssd_2tb,2
```

---

### memory.csv

```csv
id,en,fr,memory_type,capacity_gb
ddr4_4gb,4 GB DDR4,4 Go DDR4,ddr4,4
ddr4_8gb,8 GB DDR4,8 Go DDR4,ddr4,8
ddr4_16gb,16 GB DDR4,16 Go DDR4,ddr4,16
ddr4_32gb,32 GB DDR4,32 Go DDR4,ddr4,32
ddr4_64gb,64 GB DDR4,64 Go DDR4,ddr4,64
ddr4_128gb,128 GB DDR4,128 Go DDR4,ddr4,128
ddr5_8gb,8 GB DDR5,8 Go DDR5,ddr5,8
ddr5_16gb,16 GB DDR5,16 Go DDR5,ddr5,16
ddr5_24gb,24 GB DDR5,24 Go DDR5,ddr5,24
ddr5_32gb,32 GB DDR5,32 Go DDR5,ddr5,32
ddr5_48gb,48 GB DDR5,48 Go DDR5,ddr5,48
ddr5_64gb,64 GB DDR5,64 Go DDR5,ddr5,64
ddr5_96gb,96 GB DDR5,96 Go DDR5,ddr5,96
ddr5_128gb,128 GB DDR5,128 Go DDR5,ddr5,128
ddr5_192gb,192 GB DDR5,192 Go DDR5,ddr5,192
lpddr4x_4gb,4 GB LPDDR4X,4 Go LPDDR4X,lpddr4x,4
lpddr4x_8gb,8 GB LPDDR4X,8 Go LPDDR4X,lpddr4x,8
lpddr4x_16gb,16 GB LPDDR4X,16 Go LPDDR4X,lpddr4x,16
lpddr5_8gb,8 GB LPDDR5,8 Go LPDDR5,lpddr5,8
lpddr5_16gb,16 GB LPDDR5,16 Go LPDDR5,lpddr5,16
lpddr5_32gb,32 GB LPDDR5,32 Go LPDDR5,lpddr5,32
lpddr5x_16gb,16 GB LPDDR5X,16 Go LPDDR5X,lpddr5x,16
lpddr5x_24gb,24 GB LPDDR5X,24 Go LPDDR5X,lpddr5x,24
lpddr5x_32gb,32 GB LPDDR5X,32 Go LPDDR5X,lpddr5x,32
lpddr5x_64gb,64 GB LPDDR5X,64 Go LPDDR5X,lpddr5x,64
unified_8gb,8 GB Unified Memory,8 Go de mémoire unifiée,unified_memory,8
unified_16gb,16 GB Unified Memory,16 Go de mémoire unifiée,unified_memory,16
unified_24gb,24 GB Unified Memory,24 Go de mémoire unifiée,unified_memory,24
unified_32gb,32 GB Unified Memory,32 Go de mémoire unifiée,unified_memory,32
unified_36gb,36 GB Unified Memory,36 Go de mémoire unifiée,unified_memory,36
unified_48gb,48 GB Unified Memory,48 Go de mémoire unifiée,unified_memory,48
unified_64gb,64 GB Unified Memory,64 Go de mémoire unifiée,unified_memory,64
unified_96gb,96 GB Unified Memory,96 Go de mémoire unifiée,unified_memory,96
unified_128gb,128 GB Unified Memory,128 Go de mémoire unifiée,unified_memory,128
unified_192gb,192 GB Unified Memory,192 Go de mémoire unifiée,unified_memory,192
ecc_ddr4_16gb,16 GB ECC DDR4,16 Go ECC DDR4,ecc_ddr4,16
ecc_ddr4_32gb,32 GB ECC DDR4,32 Go ECC DDR4,ecc_ddr4,32
ecc_ddr4_64gb,64 GB ECC DDR4,64 Go ECC DDR4,ecc_ddr4,64
ecc_ddr4_128gb,128 GB ECC DDR4,128 Go ECC DDR4,ecc_ddr4,128
ecc_ddr4_256gb,256 GB ECC DDR4,256 Go ECC DDR4,ecc_ddr4,256
ecc_ddr5_16gb,16 GB ECC DDR5,16 Go ECC DDR5,ecc_ddr5,16
ecc_ddr5_32gb,32 GB ECC DDR5,32 Go ECC DDR5,ecc_ddr5,32
ecc_ddr5_64gb,64 GB ECC DDR5,64 Go ECC DDR5,ecc_ddr5,64
ecc_ddr5_128gb,128 GB ECC DDR5,128 Go ECC DDR5,ecc_ddr5,128
ecc_ddr5_256gb,256 GB ECC DDR5,256 Go ECC DDR5,ecc_ddr5,256
ecc_ddr5_512gb,512 GB ECC DDR5,512 Go ECC DDR5,ecc_ddr5,512
```

---

### model_form_factor.csv

```csv
product_model_id,form_factor_id
aspire_5,clamshell
swift_go_14,clamshell
travelmate_p4_14,clamshell
predator_helios_16,clamshell
nitro_v_15,clamshell
mac_mini,mini
imac_24,integrated_display
mac_studio,tower
mac_pro,tower
expertbook_b5,clamshell
proart_p16,clamshell
envy_16,clamshell
victus_16,clamshell
thinkbook_14,clamshell
loq_15,clamshell
thinkstation_p3_tower,tower
surface_studio_2_plus,integrated_display
modern_14,clamshell
prestige_14,clamshell
stealth_16,clamshell
raider_18,clamshell
vector_16,clamshell
creator_z16,clamshell
predator_orion_5000,tower
precision_3680_tower,tower
alienware_aurora,tower
omen_35l,tower
inspiron_24_aio,integrated_display
pavilion_24_aio,integrated_display
poweredge_r760,rackmount
poweredge_t560,tower
proliant_dl380,rackmount
superserver_sys_221h_tnr,rackmount
raspberry_pi_5,board
z2_tower_g9,tower
thinkpad_t14,clamshell
thinkpad_x1_carbon,clamshell
thinkpad_p14s,clamshell
ideapad_slim_5,clamshell
yoga_7,convertible_360
legion_5,clamshell
xps_13,clamshell
xps_16,clamshell
latitude_5450,clamshell
precision_5690,clamshell
optiplex_7020,small_form_factor
inspiron_16,clamshell
alienware_m16,clamshell
elitebook_840,clamshell
probook_450,clamshell
zbook_firefly_14,clamshell
pavilion_15,clamshell
omen_16,clamshell
zenbook_14,clamshell
vivobook_16,clamshell
rog_zephyrus_g14,clamshell
tuf_gaming_a15,clamshell
macbook_air_13,clamshell
macbook_air_15,clamshell
macbook_pro_14,clamshell
macbook_pro_16,clamshell
surface_laptop_13,clamshell
surface_pro_13,detachable
framework_laptop_13,clamshell
razer_blade_14,clamshell
galaxy_book5_pro_14,clamshell
thinkcentre_m90s,small_form_factor
asus_nuc_14_pro,mini
zotac_zbox_magnus,mini
```

---

### model_generation.csv

```csv
id,en,fr,product_model_id,model_year
aspire_5_a515_58m,A515-58M,A515-58M,aspire_5,2023
swift_go_14_sfg14_73,SFG14-73,SFG14-73,swift_go_14,2024
travelmate_p4_14_tmp414_53,TMP414-53,TMP414-53,travelmate_p4_14,2024
predator_helios_16_ph16_72,PH16-72,PH16-72,predator_helios_16,2024
nitro_v_15_anv15_51,ANV15-51,ANV15-51,nitro_v_15,2023
mac_mini_m4,M4,M4,mac_mini,2024
imac_24_m4,M4,M4,imac_24,2024
mac_studio_m4_max,M4 Max,M4 Max,mac_studio,2025
mac_pro_m2_ultra,M2 Ultra,M2 Ultra,mac_pro,2023
expertbook_b5_b5404,B5404,B5404,expertbook_b5,2024
proart_p16_h7606,H7606,H7606,proart_p16,2024
envy_16_2024,2024 edition,Édition 2024,envy_16,2024
victus_16_2024,2024 edition,Édition 2024,victus_16,2024
thinkbook_14_gen7,Gen 7,Gen 7,thinkbook_14,2024
loq_15_gen9,Gen 9,Gen 9,loq_15,2024
thinkstation_p3_tower_gen2,Gen 2,Gen 2,thinkstation_p3_tower,2025
surface_studio_2_plus_2022,2+,2+,surface_studio_2_plus,2022
modern_14_c13m,C13M,C13M,modern_14,2023
prestige_14_ai_studio_c1v,AI Studio C1V,AI Studio C1V,prestige_14,2024
stealth_16_ai_studio_a1v,AI Studio A1V,AI Studio A1V,stealth_16,2024
raider_18_hx_a14v,HX A14V,HX A14V,raider_18,2024
vector_16_hx_a14v,HX A14V,HX A14V,vector_16,2024
creator_z16_hx_studio_2023,HX Studio,HX Studio,creator_z16,2023
predator_orion_5000_2025,2025 edition,Édition 2025,predator_orion_5000,2025
precision_3680_tower_2024,2024 edition,Édition 2024,precision_3680_tower,2024
alienware_aurora_r16,R16,R16,alienware_aurora,2023
omen_35l_2024,2024 edition,Édition 2024,omen_35l,2024
inspiron_24_aio_5430,5430,5430,inspiron_24_aio,2024
pavilion_24_aio_2024,2024 edition,Édition 2024,pavilion_24_aio,2024
poweredge_r760_2023,2023 release,Version 2023,poweredge_r760,2023
poweredge_t560_2023,2023 release,Version 2023,poweredge_t560,2023
proliant_dl380_gen11,Gen11,Gen11,proliant_dl380,2023
superserver_sys_221h_tnr_2023,2023 release,Version 2023,superserver_sys_221h_tnr,2023
raspberry_pi_5_2023,2023 release,Version 2023,raspberry_pi_5,2023
z2_tower_g9_2022,G9,G9,z2_tower_g9,2022
thinkpad_p14s_gen5,Gen 5,Gen 5,thinkpad_p14s,2024
ideapad_slim_5_gen9,Gen 9,Gen 9,ideapad_slim_5,2024
yoga_7_gen9,Gen 9,Gen 9,yoga_7,2024
xps_13_9345,9345,9345,xps_13,2024
xps_16_9640,9640,9640,xps_16,2024
latitude_5450_2024,2024 edition,Édition 2024,latitude_5450,2024
precision_5690_2024,2024 edition,Édition 2024,precision_5690,2024
inspiron_16_5640,5640,5640,inspiron_16,2024
alienware_m16_r2,R2,R2,alienware_m16,2024
elitebook_840_g11,G11,G11,elitebook_840,2024
probook_450_g11,G11,G11,probook_450,2024
zbook_firefly_14_g11,G11,G11,zbook_firefly_14,2024
pavilion_15_2024,2024 edition,Édition 2024,pavilion_15,2024
omen_16_2024,2024 edition,Édition 2024,omen_16,2024
zenbook_14_ux3405,UX3405,UX3405,zenbook_14,2024
vivobook_16_x1605,X1605,X1605,vivobook_16,2023
rog_zephyrus_g14_ga403,GA403,GA403,rog_zephyrus_g14,2024
tuf_gaming_a15_fa507,FA507,FA507,tuf_gaming_a15,2024
macbook_air_15_m4,M4,M4,macbook_air_15,2025
surface_laptop_13_first_edition,1st Edition,1st Edition,surface_laptop_13,2025
surface_pro_13_11th_edition,11th Edition,11th Edition,surface_pro_13,2024
framework_laptop_13_2025,2025 edition,Édition 2025,framework_laptop_13,2025
razer_blade_14_2025,2025 edition,Édition 2025,razer_blade_14,2025
galaxy_book5_pro_14_2025,2025 edition,Édition 2025,galaxy_book5_pro_14,2025
thinkpad_t14_gen5,Gen 5,Gen 5,thinkpad_t14,2024
thinkpad_t14_gen6,Gen 6,Gen 6,thinkpad_t14,2025
thinkpad_x1_carbon_gen12,Gen 12,Gen 12,thinkpad_x1_carbon,2024
thinkpad_x1_carbon_gen13,Gen 13,Gen 13,thinkpad_x1_carbon,2025
legion_5_gen9,Gen 9,Gen 9,legion_5,2024
legion_5_gen10,Gen 10,Gen 10,legion_5,2025
macbook_air_m3,M3,M3,macbook_air_13,2024
macbook_air_m4,M4,M4,macbook_air_13,2025
macbook_pro_m4,M4,M4,macbook_pro_14,2024
macbook_pro_m4_pro,M4 Pro,M4 Pro,macbook_pro_14,2024
macbook_pro_m4_max,M4 Max,M4 Max,macbook_pro_16,2024
optiplex_7020_2024,2024 edition,Édition 2024,optiplex_7020,2024
thinkcentre_m90s_gen5,Gen 5,Gen 5,thinkcentre_m90s,2024
asus_nuc_14_pro_2024,2024 release,Version 2024,asus_nuc_14_pro,2024
zotac_zbox_magnus_en474070c,EN474070C,EN474070C,zotac_zbox_magnus,2024
```

---

### operating_system.csv

```csv
id,en,fr,os_family
raspberry_pi_os,Raspberry Pi OS,Raspberry Pi OS,linux
windows_11_home,Windows 11 Home,Windows 11 Famille,windows
windows_11_pro,Windows 11 Pro,Windows 11 Professionnel,windows
windows_11_education,Windows 11 Education,Windows 11 Éducation,windows
windows_11_pro_workstations,Windows 11 Pro for Workstations,Windows 11 Professionnel pour stations de travail,windows
chromeos,ChromeOS,ChromeOS,chromeos
macos,macOS,macOS,macos
ubuntu,Ubuntu,Ubuntu,linux
fedora,Fedora,Fedora,linux
debian,Debian,Debian,linux
linux_mint,Linux Mint,Linux Mint,linux
no_os,No operating system,Sans système d'exploitation,none
```

---

### product_category.csv

```csv
id,en,fr
computers,Computers,Ordinateurs
laptops,Laptops,Ordinateurs portables
desktops,Desktops,Ordinateurs de bureau
all_in_one,All-in-One Computers,Ordinateurs tout-en-un
mini_pc,Mini PCs,Mini PC
workstations,Workstations,Stations de travail
servers,Servers,Serveurs
single_board_computers,Single-board computers,Ordinateurs monocartes
```

---

### product_family.csv

```csv
id,en,fr,brand_id
poweredge,PowerEdge,PowerEdge,dell
proliant,ProLiant,ProLiant,hpe
superserver,SuperServer,SuperServer,supermicro
raspberry_pi,Raspberry Pi,Raspberry Pi,raspberry_pi
z,Z,Z,hp
aspire,Aspire,Aspire,acer
swift,Swift,Swift,acer
travelmate,TravelMate,TravelMate,acer
predator,Predator,Predator,acer
nitro,Nitro,Nitro,acer
macbook_air,MacBook Air,MacBook Air,apple
macbook_pro,MacBook Pro,MacBook Pro,apple
mac_mini,Mac mini,Mac mini,apple
imac,iMac,iMac,apple
mac_studio,Mac Studio,Mac Studio,apple
mac_pro,Mac Pro,Mac Pro,apple
vivobook,Vivobook,Vivobook,asus
zenbook,Zenbook,Zenbook,asus
expertbook,ExpertBook,ExpertBook,asus
rog,ROG,ROG,asus
tuf_gaming,TUF Gaming,TUF Gaming,asus
proart,ProArt,ProArt,asus
nuc,NUC,NUC,asus
inspiron,Inspiron,Inspiron,dell
latitude,Latitude,Latitude,dell
xps,XPS,XPS,dell
precision,Precision,Precision,dell
optiplex,OptiPlex,OptiPlex,dell
alienware,Alienware,Alienware,dell
framework_laptop,Framework Laptop,Framework Laptop,framework
probook,ProBook,ProBook,hp
elitebook,EliteBook,EliteBook,hp
zbook,ZBook,ZBook,hp
pavilion,Pavilion,Pavilion,hp
envy,Envy,Envy,hp
omen,OMEN,OMEN,hp
victus,Victus,Victus,hp
thinkpad,ThinkPad,ThinkPad,lenovo
thinkbook,ThinkBook,ThinkBook,lenovo
ideapad,IdeaPad,IdeaPad,lenovo
yoga,Yoga,Yoga,lenovo
legion,Legion,Legion,lenovo
loq,LOQ,LOQ,lenovo
thinkcentre,ThinkCentre,ThinkCentre,lenovo
thinkstation,ThinkStation,ThinkStation,lenovo
surface_laptop,Surface Laptop,Surface Laptop,microsoft
surface_pro,Surface Pro,Surface Pro,microsoft
surface_studio,Surface Studio,Surface Studio,microsoft
modern,Modern,Modern,msi
prestige,Prestige,Prestige,msi
stealth,Stealth,Stealth,msi
raider,Raider,Raider,msi
vector,Vector,Vector,msi
creator,Creator,Creator,msi
blade,Blade,Blade,razer
galaxy_book,Galaxy Book,Galaxy Book,samsung
zbox,ZBOX,ZBOX,zotac
```

---

### product_family_computer_type.csv

```csv
product_family_id,computer_type_id
inspiron,all_in_one
pavilion,all_in_one
poweredge,server
proliant,server
superserver,server
raspberry_pi,single_board_computer
z,desktop
aspire,laptop
swift,laptop
travelmate,laptop
predator,laptop
predator,desktop
nitro,laptop
macbook_air,laptop
macbook_pro,laptop
mac_mini,mini_pc
imac,all_in_one
mac_studio,desktop
mac_pro,desktop
vivobook,laptop
zenbook,laptop
expertbook,laptop
rog,laptop
rog,desktop
tuf_gaming,laptop
tuf_gaming,desktop
proart,laptop
proart,desktop
nuc,mini_pc
inspiron,laptop
inspiron,desktop
latitude,laptop
xps,laptop
xps,desktop
precision,laptop
precision,desktop
optiplex,desktop
alienware,laptop
alienware,desktop
framework_laptop,laptop
probook,laptop
elitebook,laptop
zbook,laptop
pavilion,laptop
pavilion,desktop
envy,laptop
envy,desktop
omen,laptop
omen,desktop
victus,laptop
victus,desktop
thinkpad,laptop
thinkbook,laptop
ideapad,laptop
yoga,laptop
legion,laptop
legion,desktop
loq,laptop
loq,desktop
thinkcentre,desktop
thinkstation,desktop
surface_laptop,laptop
surface_pro,laptop
surface_studio,all_in_one
modern,laptop
prestige,laptop
stealth,laptop
raider,laptop
vector,laptop
creator,laptop
blade,laptop
galaxy_book,laptop
zbox,mini_pc
```

---

### product_family_product_segment.csv

```csv
product_family_id,product_segment_id
poweredge,business
poweredge,enterprise
proliant,enterprise
superserver,enterprise
raspberry_pi,general_purpose
raspberry_pi,consumer
raspberry_pi,education
z,workstation
aspire,general_purpose
aspire,consumer
aspire,education
swift,consumer
swift,premium
travelmate,business
travelmate,enterprise
travelmate,education
predator,gaming
predator,premium
nitro,gaming
nitro,consumer
macbook_air,consumer
macbook_air,premium
macbook_air,education
macbook_pro,premium
macbook_pro,creator
macbook_pro,business
macbook_pro,workstation
mac_mini,general_purpose
mac_mini,consumer
mac_mini,business
mac_mini,creator
imac,consumer
imac,premium
imac,creator
mac_studio,premium
mac_studio,creator
mac_studio,workstation
mac_pro,workstation
mac_pro,enterprise
vivobook,consumer
vivobook,general_purpose
zenbook,premium
zenbook,consumer
expertbook,business
expertbook,enterprise
rog,gaming
rog,premium
tuf_gaming,gaming
tuf_gaming,consumer
proart,creator
proart,premium
proart,workstation
nuc,general_purpose
nuc,consumer
nuc,business
nuc,premium
nuc,creator
nuc,enterprise
inspiron,consumer
inspiron,general_purpose
latitude,business
latitude,enterprise
xps,premium
xps,business
xps,creator
precision,workstation
precision,business
precision,enterprise
optiplex,business
optiplex,enterprise
optiplex,education
alienware,gaming
alienware,premium
framework_laptop,consumer
framework_laptop,business
framework_laptop,premium
probook,business
probook,education
elitebook,business
elitebook,premium
elitebook,enterprise
zbook,workstation
zbook,creator
zbook,business
pavilion,consumer
pavilion,general_purpose
envy,consumer
envy,premium
envy,creator
omen,gaming
omen,premium
victus,gaming
victus,consumer
thinkpad,business
thinkpad,enterprise
thinkpad,premium
thinkpad,workstation
thinkbook,business
thinkbook,general_purpose
ideapad,consumer
ideapad,general_purpose
ideapad,education
yoga,consumer
yoga,premium
yoga,creator
legion,gaming
legion,premium
loq,gaming
loq,consumer
thinkcentre,business
thinkcentre,enterprise
thinkcentre,education
thinkcentre,thin_client
thinkstation,workstation
thinkstation,enterprise
surface_laptop,consumer
surface_laptop,business
surface_laptop,premium
surface_pro,business
surface_pro,premium
surface_pro,education
surface_studio,premium
surface_studio,creator
modern,consumer
modern,general_purpose
prestige,premium
prestige,business
prestige,creator
stealth,gaming
stealth,premium
raider,gaming
raider,premium
vector,gaming
vector,creator
creator,creator
creator,premium
blade,gaming
blade,premium
blade,creator
galaxy_book,consumer
galaxy_book,premium
galaxy_book,business
zbox,general_purpose
zbox,consumer
zbox,business
zbox,gaming
zbox,creator
```

---

### product_model.csv

```csv
id,en,fr,product_family_id
aspire_5,Aspire 5,Aspire 5,aspire
swift_go_14,Swift Go 14,Swift Go 14,swift
travelmate_p4_14,TravelMate P4 14,TravelMate P4 14,travelmate
predator_helios_16,Predator Helios 16,Predator Helios 16,predator
nitro_v_15,Nitro V 15,Nitro V 15,nitro
mac_mini,Mac mini,Mac mini,mac_mini
imac_24,iMac 24-inch,iMac 24-inch,imac
mac_studio,Mac Studio,Mac Studio,mac_studio
mac_pro,Mac Pro,Mac Pro,mac_pro
expertbook_b5,ExpertBook B5,ExpertBook B5,expertbook
proart_p16,ProArt P16,ProArt P16,proart
envy_16,Envy 16,Envy 16,envy
victus_16,Victus 16,Victus 16,victus
thinkbook_14,ThinkBook 14,ThinkBook 14,thinkbook
loq_15,LOQ 15,LOQ 15,loq
thinkstation_p3_tower,ThinkStation P3 Tower,ThinkStation P3 Tower,thinkstation
surface_studio_2_plus,Surface Studio 2+,Surface Studio 2+,surface_studio
modern_14,Modern 14,Modern 14,modern
prestige_14,Prestige 14,Prestige 14,prestige
stealth_16,Stealth 16,Stealth 16,stealth
raider_18,Raider 18,Raider 18,raider
vector_16,Vector 16,Vector 16,vector
creator_z16,Creator Z16,Creator Z16,creator
predator_orion_5000,Predator Orion 5000,Predator Orion 5000,predator
precision_3680_tower,Precision 3680 Tower,Precision 3680 Tower,precision
alienware_aurora,Alienware Aurora,Alienware Aurora,alienware
omen_35l,OMEN 35L,OMEN 35L,omen
inspiron_24_aio,Inspiron 24 All-in-One,Inspiron 24 All-in-One,inspiron
pavilion_24_aio,Pavilion 24 All-in-One,Pavilion 24 All-in-One,pavilion
poweredge_r760,PowerEdge R760,PowerEdge R760,poweredge
poweredge_t560,PowerEdge T560,PowerEdge T560,poweredge
proliant_dl380,ProLiant DL380,ProLiant DL380,proliant
superserver_sys_221h_tnr,SuperServer SYS-221H-TNR,SuperServer SYS-221H-TNR,superserver
raspberry_pi_5,Raspberry Pi 5,Raspberry Pi 5,raspberry_pi
z2_tower_g9,Z2 Tower G9,Z2 Tower G9,z
thinkpad_t14,ThinkPad T14,ThinkPad T14,thinkpad
thinkpad_x1_carbon,ThinkPad X1 Carbon,ThinkPad X1 Carbon,thinkpad
thinkpad_p14s,ThinkPad P14s,ThinkPad P14s,thinkpad
ideapad_slim_5,IdeaPad Slim 5,IdeaPad Slim 5,ideapad
yoga_7,Yoga 7,Yoga 7,yoga
legion_5,Legion 5,Legion 5,legion
xps_13,XPS 13,XPS 13,xps
xps_16,XPS 16,XPS 16,xps
latitude_5450,Latitude 5450,Latitude 5450,latitude
precision_5690,Precision 5690,Precision 5690,precision
optiplex_7020,OptiPlex 7020,OptiPlex 7020,optiplex
inspiron_16,Inspiron 16,Inspiron 16,inspiron
alienware_m16,Alienware m16,Alienware m16,alienware
elitebook_840,EliteBook 840,EliteBook 840,elitebook
probook_450,ProBook 450,ProBook 450,probook
zbook_firefly_14,ZBook Firefly 14,ZBook Firefly 14,zbook
pavilion_15,Pavilion 15,Pavilion 15,pavilion
omen_16,OMEN 16,OMEN 16,omen
zenbook_14,Zenbook 14,Zenbook 14,zenbook
vivobook_16,Vivobook 16,Vivobook 16,vivobook
rog_zephyrus_g14,ROG Zephyrus G14,ROG Zephyrus G14,rog
tuf_gaming_a15,TUF Gaming A15,TUF Gaming A15,tuf_gaming
macbook_air_13,MacBook Air 13-inch,MacBook Air 13 po,macbook_air
macbook_air_15,MacBook Air 15-inch,MacBook Air 15 po,macbook_air
macbook_pro_14,MacBook Pro 14-inch,MacBook Pro 14 po,macbook_pro
macbook_pro_16,MacBook Pro 16-inch,MacBook Pro 16 po,macbook_pro
surface_laptop_13,Surface Laptop 13-inch,Surface Laptop 13 po,surface_laptop
surface_pro_13,Surface Pro 13-inch,Surface Pro 13 po,surface_pro
framework_laptop_13,Framework Laptop 13,Framework Laptop 13,framework_laptop
razer_blade_14,Razer Blade 14,Razer Blade 14,blade
galaxy_book5_pro_14,Galaxy Book5 Pro 14,Galaxy Book5 Pro 14,galaxy_book
thinkcentre_m90s,ThinkCentre M90s,ThinkCentre M90s,thinkcentre
asus_nuc_14_pro,ASUS NUC 14 Pro,ASUS NUC 14 Pro,nuc
zotac_zbox_magnus,ZOTAC ZBOX MAGNUS,ZOTAC ZBOX MAGNUS,zbox
```

---

### product_segment.csv

```csv
id,en,fr,product_subcategory_id
general_purpose,General purpose,Usage général,
consumer,Consumer,Grand public,
business,Business,Professionnel,
premium,Premium,Haut de gamme,
gaming,Gaming,Jeu vidéo,
workstation,Workstation,Station de travail,
creator,Creator,Création,
education,Education,Éducation,
enterprise,Enterprise,Entreprise,
thin_client,Thin client,Client léger,
```

---

### product_segment_brand.csv

```csv
product_segment_id,brand_id
general_purpose,raspberry_pi
consumer,raspberry_pi
education,raspberry_pi
general_purpose,acer
general_purpose,apple
general_purpose,asus
general_purpose,dell
general_purpose,framework
general_purpose,hp
general_purpose,lenovo
general_purpose,lg
general_purpose,microsoft
general_purpose,msi
general_purpose,samsung
general_purpose,zotac
consumer,acer
consumer,apple
consumer,asus
consumer,dell
consumer,framework
consumer,hp
consumer,lenovo
consumer,lg
consumer,microsoft
consumer,msi
consumer,razer
consumer,samsung
consumer,zotac
business,acer
business,apple
business,asus
business,dell
business,framework
business,hp
business,lenovo
business,lg
business,microsoft
business,samsung
business,zotac
premium,acer
premium,apple
premium,asus
premium,dell
premium,framework
premium,hp
premium,lenovo
premium,lg
premium,microsoft
premium,msi
premium,razer
premium,samsung
premium,zotac
gaming,acer
gaming,asus
gaming,dell
gaming,gigabyte
gaming,hp
gaming,lenovo
gaming,msi
gaming,razer
gaming,zotac
workstation,apple
workstation,asus
workstation,dell
workstation,gigabyte
workstation,hp
workstation,lenovo
workstation,msi
workstation,supermicro
creator,apple
creator,asus
creator,dell
creator,gigabyte
creator,hp
creator,lenovo
creator,lg
creator,microsoft
creator,msi
creator,razer
creator,samsung
creator,zotac
education,acer
education,apple
education,asus
education,dell
education,hp
education,lenovo
education,microsoft
education,samsung
enterprise,acer
enterprise,asus
enterprise,dell
enterprise,hp
enterprise,hpe
enterprise,lenovo
enterprise,microsoft
enterprise,supermicro
thin_client,acer
thin_client,dell
thin_client,hp
thin_client,lenovo
```

---

### product_segment_display_weight.csv

```csv
product_segment_id,display_id,weight
consumer,ips_11_6_hd_60,7
consumer,ips_12_4_fhd_60_touch,7
consumer,ips_13_3_fhd_60,7
consumer,ips_13_3_fhd_60_touch,7
consumer,ips_13_6_2560_1664_60,7
consumer,ips_14_5_qhdplus_120,7
consumer,ips_14_qhdplus_120,7
consumer,ips_14_wuxga_120,7
consumer,ips_14_wuxga_60,7
consumer,ips_14_wuxga_60_touch,7
consumer,ips_15_3_2880_1864_60,7
consumer,ips_15_6_fhd_144,7
consumer,ips_15_6_fhd_165,7
consumer,ips_15_6_fhd_60,7
consumer,ips_16_qhdplus_165,7
consumer,ips_16_qhdplus_240,7
consumer,ips_16_wuxga_120,7
consumer,ips_16_wuxga_60,7
consumer,ips_17_3_fhd_144,7
consumer,ips_17_3_qhd_240,7
consumer,ips_21_5_fhd_60,7
consumer,ips_23_8_fhd_60,7
consumer,ips_24_fhd_75,7
consumer,ips_27_4k_60,7
consumer,ips_27_5k_60,7
consumer,ips_27_qhd_60,7
consumer,oled_14_2_8k_120,2
consumer,oled_14_2_8k_120_touch,2
consumer,oled_14_2_8k_90,2
consumer,oled_14_5_3k_120_touch,2
consumer,oled_15_6_2_8k_120,2
consumer,oled_16_3_2k_120,2
consumer,oled_27_qhd_240,2
business,ips_11_6_hd_60,8
business,ips_12_4_fhd_60_touch,8
business,ips_13_3_fhd_60,8
business,ips_13_3_fhd_60_touch,8
business,ips_13_6_2560_1664_60,8
business,ips_14_5_qhdplus_120,8
business,ips_14_qhdplus_120,8
business,ips_14_wuxga_120,8
business,ips_14_wuxga_60,8
business,ips_14_wuxga_60_touch,8
business,ips_15_3_2880_1864_60,8
business,ips_15_6_fhd_144,8
business,ips_15_6_fhd_165,8
business,ips_15_6_fhd_60,8
business,ips_16_qhdplus_165,8
business,ips_16_qhdplus_240,8
business,ips_16_wuxga_120,8
business,ips_16_wuxga_60,8
business,ips_17_3_fhd_144,8
business,ips_17_3_qhd_240,8
business,ips_21_5_fhd_60,8
business,ips_23_8_fhd_60,8
business,ips_24_fhd_75,8
business,ips_27_4k_60,8
business,ips_27_5k_60,8
business,ips_27_qhd_60,8
business,oled_14_2_8k_120,1
business,oled_14_2_8k_120_touch,1
business,oled_14_2_8k_90,1
business,oled_14_5_3k_120_touch,1
business,oled_15_6_2_8k_120,1
business,oled_16_3_2k_120,1
business,oled_27_qhd_240,1
premium,ips_11_6_hd_60,3
premium,ips_12_4_fhd_60_touch,3
premium,ips_13_3_fhd_60,3
premium,ips_13_3_fhd_60_touch,3
premium,ips_13_6_2560_1664_60,3
premium,ips_14_5_qhdplus_120,3
premium,ips_14_qhdplus_120,3
premium,ips_14_wuxga_120,3
premium,ips_14_wuxga_60,3
premium,ips_14_wuxga_60_touch,3
premium,ips_15_3_2880_1864_60,3
premium,ips_15_6_fhd_144,3
premium,ips_15_6_fhd_165,3
premium,ips_15_6_fhd_60,3
premium,ips_16_qhdplus_165,3
premium,ips_16_qhdplus_240,3
premium,ips_16_wuxga_120,3
premium,ips_16_wuxga_60,3
premium,ips_17_3_fhd_144,3
premium,ips_17_3_qhd_240,3
premium,ips_21_5_fhd_60,3
premium,ips_23_8_fhd_60,3
premium,ips_24_fhd_75,3
premium,ips_27_4k_60,3
premium,ips_27_5k_60,3
premium,ips_27_qhd_60,3
premium,oled_14_2_8k_120,6
premium,oled_14_2_8k_120_touch,6
premium,oled_14_2_8k_90,6
premium,oled_14_5_3k_120_touch,6
premium,oled_15_6_2_8k_120,6
premium,oled_16_3_2k_120,6
premium,oled_27_qhd_240,6
premium,mini_led_16_qhdplus_240,3
gaming,ips_11_6_hd_60,6
gaming,ips_12_4_fhd_60_touch,6
gaming,ips_13_3_fhd_60,6
gaming,ips_13_3_fhd_60_touch,6
gaming,ips_13_6_2560_1664_60,6
gaming,ips_14_5_qhdplus_120,6
gaming,ips_14_qhdplus_120,6
gaming,ips_14_wuxga_120,6
gaming,ips_14_wuxga_60,6
gaming,ips_14_wuxga_60_touch,6
gaming,ips_15_3_2880_1864_60,6
gaming,ips_15_6_fhd_144,6
gaming,ips_15_6_fhd_165,6
gaming,ips_15_6_fhd_60,6
gaming,ips_16_qhdplus_165,6
gaming,ips_16_qhdplus_240,6
gaming,ips_16_wuxga_120,6
gaming,ips_16_wuxga_60,6
gaming,ips_17_3_fhd_144,6
gaming,ips_17_3_qhd_240,6
gaming,ips_21_5_fhd_60,6
gaming,ips_23_8_fhd_60,6
gaming,ips_24_fhd_75,6
gaming,ips_27_4k_60,6
gaming,ips_27_5k_60,6
gaming,ips_27_qhd_60,6
gaming,oled_14_2_8k_120,4
gaming,oled_14_2_8k_120_touch,4
gaming,oled_14_2_8k_90,4
gaming,oled_14_5_3k_120_touch,4
gaming,oled_15_6_2_8k_120,4
gaming,oled_16_3_2k_120,4
gaming,oled_27_qhd_240,4
gaming,mini_led_16_qhdplus_240,2
creator,ips_11_6_hd_60,3
creator,ips_12_4_fhd_60_touch,3
creator,ips_13_3_fhd_60,3
creator,ips_13_3_fhd_60_touch,3
creator,ips_13_6_2560_1664_60,3
creator,ips_14_5_qhdplus_120,3
creator,ips_14_qhdplus_120,3
creator,ips_14_wuxga_120,3
creator,ips_14_wuxga_60,3
creator,ips_14_wuxga_60_touch,3
creator,ips_15_3_2880_1864_60,3
creator,ips_15_6_fhd_144,3
creator,ips_15_6_fhd_165,3
creator,ips_15_6_fhd_60,3
creator,ips_16_qhdplus_165,3
creator,ips_16_qhdplus_240,3
creator,ips_16_wuxga_120,3
creator,ips_16_wuxga_60,3
creator,ips_17_3_fhd_144,3
creator,ips_17_3_qhd_240,3
creator,ips_21_5_fhd_60,3
creator,ips_23_8_fhd_60,3
creator,ips_24_fhd_75,3
creator,ips_27_4k_60,3
creator,ips_27_5k_60,3
creator,ips_27_qhd_60,3
creator,oled_14_2_8k_120,5
creator,oled_14_2_8k_120_touch,5
creator,oled_14_2_8k_90,5
creator,oled_14_5_3k_120_touch,5
creator,oled_15_6_2_8k_120,5
creator,oled_16_3_2k_120,5
creator,oled_27_qhd_240,5
creator,mini_led_16_qhdplus_240,4
workstation,ips_11_6_hd_60,6
workstation,ips_12_4_fhd_60_touch,6
workstation,ips_13_3_fhd_60,6
workstation,ips_13_3_fhd_60_touch,6
workstation,ips_13_6_2560_1664_60,6
workstation,ips_14_5_qhdplus_120,6
workstation,ips_14_qhdplus_120,6
workstation,ips_14_wuxga_120,6
workstation,ips_14_wuxga_60,6
workstation,ips_14_wuxga_60_touch,6
workstation,ips_15_3_2880_1864_60,6
workstation,ips_15_6_fhd_144,6
workstation,ips_15_6_fhd_165,6
workstation,ips_15_6_fhd_60,6
workstation,ips_16_qhdplus_165,6
workstation,ips_16_qhdplus_240,6
workstation,ips_16_wuxga_120,6
workstation,ips_16_wuxga_60,6
workstation,ips_17_3_fhd_144,6
workstation,ips_17_3_qhd_240,6
workstation,ips_21_5_fhd_60,6
workstation,ips_23_8_fhd_60,6
workstation,ips_24_fhd_75,6
workstation,ips_27_4k_60,6
workstation,ips_27_5k_60,6
workstation,ips_27_qhd_60,6
workstation,oled_14_2_8k_120,3
workstation,oled_14_2_8k_120_touch,3
workstation,oled_14_2_8k_90,3
workstation,oled_14_5_3k_120_touch,3
workstation,oled_15_6_2_8k_120,3
workstation,oled_16_3_2k_120,3
workstation,oled_27_qhd_240,3
```

---

### product_segment_memory_weight.csv

```csv
product_segment_id,memory_id,weight
general_purpose,ddr4_8gb,4
general_purpose,ddr4_16gb,6
general_purpose,ddr4_32gb,2
general_purpose,ddr5_8gb,4
general_purpose,ddr5_16gb,7
general_purpose,ddr5_24gb,3
general_purpose,ddr5_32gb,4
general_purpose,lpddr4x_8gb,4
general_purpose,lpddr4x_16gb,6
general_purpose,lpddr5_8gb,4
general_purpose,lpddr5_16gb,6
general_purpose,lpddr5_32gb,2
general_purpose,lpddr5x_16gb,6
general_purpose,lpddr5x_24gb,3
general_purpose,lpddr5x_32gb,4
general_purpose,unified_8gb,4
general_purpose,unified_16gb,6
general_purpose,unified_24gb,2
consumer,ddr4_4gb,1
consumer,ddr4_8gb,5
consumer,ddr4_16gb,7
consumer,ddr4_32gb,2
consumer,ddr5_8gb,5
consumer,ddr5_16gb,8
consumer,ddr5_24gb,3
consumer,ddr5_32gb,4
consumer,lpddr4x_4gb,1
consumer,lpddr4x_8gb,5
consumer,lpddr4x_16gb,7
consumer,lpddr5_8gb,5
consumer,lpddr5_16gb,7
consumer,lpddr5_32gb,3
consumer,lpddr5x_16gb,7
consumer,lpddr5x_24gb,4
consumer,lpddr5x_32gb,4
consumer,unified_8gb,4
consumer,unified_16gb,7
consumer,unified_24gb,4
consumer,unified_32gb,2
business,ddr4_8gb,2
business,ddr4_16gb,6
business,ddr4_32gb,5
business,ddr4_64gb,1
business,ddr5_8gb,2
business,ddr5_16gb,7
business,ddr5_24gb,3
business,ddr5_32gb,7
business,ddr5_48gb,2
business,ddr5_64gb,3
business,lpddr5_16gb,5
business,lpddr5_32gb,5
business,lpddr5x_16gb,6
business,lpddr5x_24gb,3
business,lpddr5x_32gb,7
business,lpddr5x_64gb,2
business,unified_16gb,6
business,unified_24gb,4
business,unified_32gb,5
business,unified_48gb,2
premium,ddr5_16gb,2
premium,ddr5_24gb,3
premium,ddr5_32gb,7
premium,ddr5_48gb,5
premium,ddr5_64gb,6
premium,ddr5_96gb,2
premium,lpddr5x_16gb,2
premium,lpddr5x_24gb,3
premium,lpddr5x_32gb,7
premium,lpddr5x_64gb,6
premium,unified_16gb,3
premium,unified_24gb,5
premium,unified_32gb,7
premium,unified_36gb,5
premium,unified_48gb,6
premium,unified_64gb,4
gaming,ddr4_16gb,3
gaming,ddr4_32gb,5
gaming,ddr4_64gb,2
gaming,ddr5_16gb,4
gaming,ddr5_24gb,2
gaming,ddr5_32gb,8
gaming,ddr5_48gb,4
gaming,ddr5_64gb,6
gaming,ddr5_96gb,2
gaming,ddr5_128gb,1
workstation,ddr5_32gb,3
workstation,ddr5_48gb,3
workstation,ddr5_64gb,6
workstation,ddr5_96gb,5
workstation,ddr5_128gb,4
workstation,ddr5_192gb,2
workstation,unified_32gb,2
workstation,unified_36gb,3
workstation,unified_48gb,5
workstation,unified_64gb,6
workstation,unified_96gb,5
workstation,unified_128gb,4
workstation,unified_192gb,2
workstation,ecc_ddr4_32gb,2
workstation,ecc_ddr4_64gb,4
workstation,ecc_ddr4_128gb,3
workstation,ecc_ddr4_256gb,1
workstation,ecc_ddr5_32gb,3
workstation,ecc_ddr5_64gb,6
workstation,ecc_ddr5_128gb,5
workstation,ecc_ddr5_256gb,3
workstation,ecc_ddr5_512gb,1
creator,ddr5_16gb,2
creator,ddr5_24gb,3
creator,ddr5_32gb,6
creator,ddr5_48gb,5
creator,ddr5_64gb,7
creator,ddr5_96gb,4
creator,ddr5_128gb,2
creator,lpddr5x_16gb,2
creator,lpddr5x_24gb,3
creator,lpddr5x_32gb,6
creator,lpddr5x_64gb,5
creator,unified_16gb,2
creator,unified_24gb,4
creator,unified_32gb,5
creator,unified_36gb,4
creator,unified_48gb,7
creator,unified_64gb,6
creator,unified_96gb,3
creator,unified_128gb,2
education,ddr4_4gb,3
education,ddr4_8gb,7
education,ddr4_16gb,5
education,ddr4_32gb,1
education,ddr5_8gb,6
education,ddr5_16gb,7
education,ddr5_24gb,2
education,ddr5_32gb,2
education,lpddr4x_4gb,4
education,lpddr4x_8gb,7
education,lpddr4x_16gb,4
education,lpddr5_8gb,6
education,lpddr5_16gb,6
education,lpddr5_32gb,2
education,lpddr5x_16gb,6
education,lpddr5x_24gb,2
education,lpddr5x_32gb,2
education,unified_8gb,5
education,unified_16gb,6
education,unified_24gb,2
enterprise,ddr4_16gb,2
enterprise,ddr4_32gb,4
enterprise,ddr4_64gb,3
enterprise,ddr4_128gb,1
enterprise,ddr5_16gb,2
enterprise,ddr5_32gb,5
enterprise,ddr5_48gb,2
enterprise,ddr5_64gb,6
enterprise,ddr5_96gb,3
enterprise,ddr5_128gb,4
enterprise,ddr5_192gb,2
enterprise,ecc_ddr4_16gb,1
enterprise,ecc_ddr4_32gb,3
enterprise,ecc_ddr4_64gb,5
enterprise,ecc_ddr4_128gb,6
enterprise,ecc_ddr4_256gb,4
enterprise,ecc_ddr5_16gb,1
enterprise,ecc_ddr5_32gb,3
enterprise,ecc_ddr5_64gb,5
enterprise,ecc_ddr5_128gb,7
enterprise,ecc_ddr5_256gb,6
enterprise,ecc_ddr5_512gb,4
thin_client,ddr4_4gb,5
thin_client,ddr4_8gb,8
thin_client,ddr4_16gb,4
thin_client,ddr4_32gb,1
thin_client,ddr5_8gb,7
thin_client,ddr5_16gb,6
thin_client,ddr5_32gb,2
thin_client,lpddr4x_4gb,5
thin_client,lpddr4x_8gb,8
thin_client,lpddr4x_16gb,4
thin_client,lpddr5_8gb,7
thin_client,lpddr5_16gb,6
thin_client,lpddr5_32gb,2
thin_client,lpddr5x_16gb,6
thin_client,lpddr5x_24gb,2
thin_client,lpddr5x_32gb,2
```

---

### product_segment_storage_weight.csv

```csv
product_segment_id,storage_id,weight
consumer,emmc_256gb,1
consumer,nvme_ssd_256gb,1
consumer,sata_ssd_256gb,1
consumer,ufs_256gb,1
consumer,nvme_ssd_512gb,6
consumer,pcie_ssd_512gb,6
consumer,sata_ssd_512gb,6
consumer,ufs_512gb,6
consumer,hdd_1tb,5
consumer,nvme_ssd_1tb,5
consumer,pcie_ssd_1tb,5
consumer,sata_ssd_1tb,5
consumer,ufs_1tb,5
business,nvme_ssd_512gb,5
business,pcie_ssd_512gb,5
business,sata_ssd_512gb,5
business,ufs_512gb,5
business,hdd_1tb,6
business,nvme_ssd_1tb,6
business,pcie_ssd_1tb,6
business,sata_ssd_1tb,6
business,ufs_1tb,6
business,hdd_2tb,2
business,nvme_ssd_2tb,2
business,pcie_ssd_2tb,2
business,sata_ssd_2tb,2
gaming,nvme_ssd_512gb,1
gaming,pcie_ssd_512gb,1
gaming,sata_ssd_512gb,1
gaming,ufs_512gb,1
gaming,hdd_1tb,6
gaming,nvme_ssd_1tb,6
gaming,pcie_ssd_1tb,6
gaming,sata_ssd_1tb,6
gaming,ufs_1tb,6
gaming,hdd_2tb,5
gaming,nvme_ssd_2tb,5
gaming,pcie_ssd_2tb,5
gaming,sata_ssd_2tb,5
gaming,hdd_4tb,2
gaming,nvme_ssd_4tb,2
gaming,pcie_ssd_4tb,2
gaming,sata_ssd_4tb,2
creator,hdd_1tb,4
creator,nvme_ssd_1tb,4
creator,pcie_ssd_1tb,4
creator,sata_ssd_1tb,4
creator,ufs_1tb,4
creator,hdd_2tb,6
creator,nvme_ssd_2tb,6
creator,pcie_ssd_2tb,6
creator,sata_ssd_2tb,6
creator,hdd_4tb,3
creator,nvme_ssd_4tb,3
creator,pcie_ssd_4tb,3
creator,sata_ssd_4tb,3
workstation,hdd_1tb,3
workstation,nvme_ssd_1tb,3
workstation,pcie_ssd_1tb,3
workstation,sata_ssd_1tb,3
workstation,ufs_1tb,3
workstation,hdd_2tb,6
workstation,nvme_ssd_2tb,6
workstation,pcie_ssd_2tb,6
workstation,sata_ssd_2tb,6
workstation,hdd_4tb,5
workstation,nvme_ssd_4tb,5
workstation,pcie_ssd_4tb,5
workstation,sata_ssd_4tb,5
workstation,hdd_8tb,2
workstation,nvme_ssd_8tb,2
workstation,pcie_ssd_8tb,2
```

---

### product_subcategory.csv

```csv
id,en,fr,product_category_id
consumer_laptop,Consumer laptop,Ordinateur portable grand public,laptops
business_laptop,Business laptop,Ordinateur portable professionnel,laptops
gaming_laptop,Gaming laptop,Ordinateur portable de jeu,laptops
creator_laptop,Creator laptop,Ordinateur portable pour création,laptops
mobile_workstation,Mobile workstation,Station de travail mobile,workstations
convertible_laptop,Convertible laptop,Ordinateur portable convertible,laptops
detachable_laptop,Detachable laptop,Ordinateur portable détachable,laptops
consumer_desktop,Consumer desktop,Ordinateur de bureau grand public,desktops
business_desktop,Business desktop,Ordinateur de bureau professionnel,desktops
gaming_desktop,Gaming desktop,Ordinateur de bureau de jeu,desktops
desktop_workstation,Desktop workstation,Station de travail de bureau,workstations
small_form_factor_pc,Small form factor PC,PC petit format,desktops
micro_pc,Micro PC,Micro PC,desktops
mini_pc,Mini PC,Mini PC,mini_pc
all_in_one_pc,All-in-One PC,PC tout-en-un,all_in_one
rack_server,Rack server,Serveur en rack,servers
tower_server,Tower server,Serveur tour,servers
blade_server,Blade server,Serveur lame,servers
single_board_computer,Single-board computer,Ordinateur monocarte,single_board_computers
```

---

### profile_exclusions.csv

```csv
scope_id,condition_field,condition_id,target_field,target_id,action
portable_only,computer_type_id,desktop,computer_type_id,desktop,exclude
portable_only,computer_type_id,all_in_one,computer_type_id,all_in_one,exclude
portable_only,computer_type_id,mini_pc,computer_type_id,mini_pc,exclude
portable_only,computer_type_id,single_board_computer,computer_type_id,single_board_computer,exclude
portable_only,computer_type_id,server,computer_type_id,server,exclude
global,computer_type_id,laptop,display_id,none,exclude
global,computer_type_id,all_in_one,display_id,none,exclude
global,computer_type_id,server,operating_system_id,windows_11_home,exclude
global,computer_type_id,server,operating_system_id,windows_11_education,exclude
global,computer_type_id,server,operating_system_id,chromeos,exclude
global,computer_type_id,server,operating_system_id,macos,exclude
global,product_segment_id,gaming,memory_id,ddr4_4gb,exclude
global,product_segment_id,gaming,memory_id,lpddr4x_4gb,exclude
global,product_segment_id,gaming,memory_id,lpddr5_8gb,exclude
global,product_segment_id,gaming,memory_id,unified_8gb,exclude
global,product_segment_id,workstation,memory_id,ddr4_4gb,exclude
global,product_segment_id,workstation,memory_id,ddr4_8gb,exclude
global,product_segment_id,workstation,memory_id,ddr5_8gb,exclude
global,product_segment_id,workstation,memory_id,lpddr4x_4gb,exclude
global,product_segment_id,workstation,memory_id,lpddr4x_8gb,exclude
global,product_segment_id,workstation,memory_id,lpddr5_8gb,exclude
global,product_segment_id,workstation,memory_id,unified_8gb,exclude
global,product_segment_id,creator,memory_id,ddr4_4gb,exclude
global,product_segment_id,creator,memory_id,lpddr4x_4gb,exclude
global,product_segment_id,creator,memory_id,lpddr5_8gb,exclude
global,product_segment_id,enterprise,memory_id,ddr4_4gb,exclude
global,product_segment_id,enterprise,memory_id,lpddr4x_4gb,exclude
global,product_segment_id,thin_client,memory_id,ddr5_64gb,exclude
global,product_segment_id,thin_client,memory_id,ddr5_96gb,exclude
global,product_segment_id,thin_client,memory_id,ddr5_128gb,exclude
global,product_segment_id,thin_client,memory_id,ddr5_192gb,exclude
global,product_segment_id,thin_client,memory_id,lpddr5x_64gb,exclude
global,product_segment_id,thin_client,memory_id,ecc_ddr4_64gb,exclude
global,product_segment_id,thin_client,memory_id,ecc_ddr4_128gb,exclude
global,product_segment_id,thin_client,memory_id,ecc_ddr4_256gb,exclude
global,product_segment_id,thin_client,memory_id,ecc_ddr5_64gb,exclude
global,product_segment_id,thin_client,memory_id,ecc_ddr5_128gb,exclude
global,product_segment_id,thin_client,memory_id,ecc_ddr5_256gb,exclude
global,product_segment_id,thin_client,memory_id,ecc_ddr5_512gb,exclude
global,product_segment_id,thin_client,gpu_id,rtx_5090,exclude
global,product_segment_id,thin_client,gpu_id,rtx_5080,exclude
global,product_segment_id,thin_client,gpu_id,rtx_5070_ti,exclude
global,product_segment_id,thin_client,gpu_id,rtx_5070,exclude
global,product_segment_id,thin_client,gpu_id,rtx_4090,exclude
global,product_segment_id,thin_client,gpu_id,rtx_4080,exclude
global,product_segment_id,thin_client,gpu_id,rx_9070_xt,exclude
global,product_segment_id,thin_client,gpu_id,rx_9070,exclude
global,product_segment_id,thin_client,gpu_id,rx_7900_xtx,exclude
global,product_segment_id,education,gpu_id,rtx_5090,exclude
global,product_segment_id,education,gpu_id,rtx_5080,exclude
global,product_segment_id,education,gpu_id,rtx_4090,exclude
global,product_segment_id,education,gpu_id,rx_9070_xt,exclude
global,product_segment_id,education,gpu_id,rx_7900_xtx,exclude
global,operating_system_id,macos,brand_id,acer,exclude
global,operating_system_id,macos,brand_id,asus,exclude
global,operating_system_id,macos,brand_id,dell,exclude
global,operating_system_id,macos,brand_id,framework,exclude
global,operating_system_id,macos,brand_id,gigabyte,exclude
global,operating_system_id,macos,brand_id,hp,exclude
global,operating_system_id,macos,brand_id,hpe,exclude
global,operating_system_id,macos,brand_id,lenovo,exclude
global,operating_system_id,macos,brand_id,lg,exclude
global,operating_system_id,macos,brand_id,microsoft,exclude
global,operating_system_id,macos,brand_id,msi,exclude
global,operating_system_id,macos,brand_id,razer,exclude
global,operating_system_id,macos,brand_id,samsung,exclude
global,operating_system_id,macos,brand_id,supermicro,exclude
global,operating_system_id,macos,brand_id,zotac,exclude
global,brand_id,apple,operating_system_id,windows_11_home,exclude
global,brand_id,apple,operating_system_id,windows_11_pro,exclude
global,brand_id,apple,operating_system_id,windows_11_education,exclude
global,brand_id,apple,operating_system_id,windows_11_pro_workstations,exclude
global,brand_id,apple,operating_system_id,chromeos,exclude
global,brand_id,apple,memory_id,ddr4_4gb,exclude
global,brand_id,apple,memory_id,ddr4_8gb,exclude
global,brand_id,apple,memory_id,ddr4_16gb,exclude
global,brand_id,apple,memory_id,ddr4_32gb,exclude
global,brand_id,apple,memory_id,ddr4_64gb,exclude
global,brand_id,apple,memory_id,ddr4_128gb,exclude
global,brand_id,apple,memory_id,ddr5_8gb,exclude
global,brand_id,apple,memory_id,ddr5_16gb,exclude
global,brand_id,apple,memory_id,ddr5_24gb,exclude
global,brand_id,apple,memory_id,ddr5_32gb,exclude
global,brand_id,apple,memory_id,ddr5_48gb,exclude
global,brand_id,apple,memory_id,ddr5_64gb,exclude
global,brand_id,apple,memory_id,ddr5_96gb,exclude
global,brand_id,apple,memory_id,ddr5_128gb,exclude
global,brand_id,apple,memory_id,ddr5_192gb,exclude
global,brand_id,apple,memory_id,lpddr4x_4gb,exclude
global,brand_id,apple,memory_id,lpddr4x_8gb,exclude
global,brand_id,apple,memory_id,lpddr4x_16gb,exclude
global,brand_id,apple,memory_id,lpddr5_8gb,exclude
global,brand_id,apple,memory_id,lpddr5_16gb,exclude
global,brand_id,apple,memory_id,lpddr5_32gb,exclude
global,brand_id,apple,memory_id,lpddr5x_16gb,exclude
global,brand_id,apple,memory_id,lpddr5x_24gb,exclude
global,brand_id,apple,memory_id,lpddr5x_32gb,exclude
global,brand_id,apple,memory_id,lpddr5x_64gb,exclude
global,brand_id,apple,memory_id,ecc_ddr4_16gb,exclude
global,brand_id,apple,memory_id,ecc_ddr4_32gb,exclude
global,brand_id,apple,memory_id,ecc_ddr4_64gb,exclude
global,brand_id,apple,memory_id,ecc_ddr4_128gb,exclude
global,brand_id,apple,memory_id,ecc_ddr4_256gb,exclude
global,brand_id,apple,memory_id,ecc_ddr5_16gb,exclude
global,brand_id,apple,memory_id,ecc_ddr5_32gb,exclude
global,brand_id,apple,memory_id,ecc_ddr5_64gb,exclude
global,brand_id,apple,memory_id,ecc_ddr5_128gb,exclude
global,brand_id,apple,memory_id,ecc_ddr5_256gb,exclude
global,brand_id,apple,memory_id,ecc_ddr5_512gb,exclude
```

---

### promotion_status.csv

```csv
id,en,fr
none,No promotion,Aucune promotion
scheduled,Scheduled,Planifiée
active,Active,Active
expired,Expired,Expirée
cancelled,Cancelled,Annulée
```

---

### promotion_type.csv

```csv
id,en,fr
none,No promotion,Aucune promotion
percentage_discount,Percentage discount,Rabais en pourcentage
fixed_discount,Fixed discount,Rabais fixe
instant_rebate,Instant rebate,Rabais instantané
coupon,Coupon,Coupon
bundle,Bundle offer,Offre groupée
clearance,Clearance,Liquidation
seasonal,Seasonal promotion,Promotion saisonnière
member_price,Member price,Prix membre
student_discount,Student discount,Rabais étudiant
business_discount,Business discount,Rabais entreprise
```

---

### seller.csv

```csv
id,en,fr,market,seller_type_id
acer_direct_ca,Acer Canada,Acer Canada,ca,manufacturer
apple_direct_ca,Apple Canada,Apple Canada,ca,manufacturer
asus_direct_ca,ASUS Canada,ASUS Canada,ca,manufacturer
dell_direct_ca,Dell Canada,Dell Canada,ca,manufacturer
framework_direct_ca,Framework Canada,Framework Canada,ca,manufacturer
hp_direct_ca,HP Canada,HP Canada,ca,manufacturer
lenovo_direct_ca,Lenovo Canada,Lenovo Canada,ca,manufacturer
microsoft_direct_ca,Microsoft Canada,Microsoft Canada,ca,manufacturer
msi_direct_ca,MSI Canada,MSI Canada,ca,manufacturer
razer_direct_ca,Razer Canada,Razer Canada,ca,manufacturer
samsung_direct_ca,Samsung Canada,Samsung Canada,ca,manufacturer
tech_store_ca,Tech Store Canada,Boutique Tech Canada,ca,retailer
computer_shop_ca,Computer Shop Canada,Boutique Informatique Canada,ca,retailer
business_it_ca,Business IT Canada,TI Entreprise Canada,ca,authorized_reseller
marketplace_vendor_ca,Marketplace Vendor Canada,Vendeur Marketplace Canada,ca,marketplace_seller
it_distributor_ca,IT Distributor Canada,Distributeur TI Canada,ca,distributor
refurbished_computers_ca,Refurbished Computers Canada,Ordinateurs reconditionnés Canada,ca,refurbisher
acer_direct_us,Acer United States,Acer États-Unis,us,manufacturer
apple_direct_us,Apple United States,Apple États-Unis,us,manufacturer
asus_direct_us,ASUS United States,ASUS États-Unis,us,manufacturer
dell_direct_us,Dell United States,Dell États-Unis,us,manufacturer
framework_direct_us,Framework United States,Framework États-Unis,us,manufacturer
hp_direct_us,HP United States,HP États-Unis,us,manufacturer
lenovo_direct_us,Lenovo United States,Lenovo États-Unis,us,manufacturer
microsoft_direct_us,Microsoft United States,Microsoft États-Unis,us,manufacturer
msi_direct_us,MSI United States,MSI États-Unis,us,manufacturer
razer_direct_us,Razer United States,Razer États-Unis,us,manufacturer
samsung_direct_us,Samsung United States,Samsung États-Unis,us,manufacturer
tech_store_us,Tech Store USA,Boutique Tech USA,us,retailer
computer_shop_us,Computer Shop USA,Boutique Informatique USA,us,retailer
business_it_us,Business IT USA,TI Entreprise USA,us,authorized_reseller
marketplace_vendor_us,Marketplace Vendor USA,Vendeur Marketplace USA,us,marketplace_seller
it_distributor_us,IT Distributor USA,Distributeur TI USA,us,distributor
refurbished_computers_us,Refurbished Computers USA,Ordinateurs reconditionnés USA,us,refurbisher
acer_direct_eu,Acer Europe,Acer Europe,eu,manufacturer
apple_direct_eu,Apple Europe,Apple Europe,eu,manufacturer
asus_direct_eu,ASUS Europe,ASUS Europe,eu,manufacturer
dell_direct_eu,Dell Europe,Dell Europe,eu,manufacturer
framework_direct_eu,Framework Europe,Framework Europe,eu,manufacturer
hp_direct_eu,HP Europe,HP Europe,eu,manufacturer
lenovo_direct_eu,Lenovo Europe,Lenovo Europe,eu,manufacturer
microsoft_direct_eu,Microsoft Europe,Microsoft Europe,eu,manufacturer
msi_direct_eu,MSI Europe,MSI Europe,eu,manufacturer
razer_direct_eu,Razer Europe,Razer Europe,eu,manufacturer
samsung_direct_eu,Samsung Europe,Samsung Europe,eu,manufacturer
tech_store_eu,Tech Store Europe,Boutique Tech Europe,eu,retailer
computer_shop_eu,Computer Shop Europe,Boutique Informatique Europe,eu,retailer
business_it_eu,Business IT Europe,TI Entreprise Europe,eu,authorized_reseller
marketplace_vendor_eu,Marketplace Vendor Europe,Vendeur Marketplace Europe,eu,marketplace_seller
it_distributor_eu,IT Distributor Europe,Distributeur TI Europe,eu,distributor
refurbished_computers_eu,Refurbished Computers Europe,Ordinateurs reconditionnés Europe,eu,refurbisher
```

---

### seller_type.csv

```csv
id,en,fr
manufacturer,Manufacturer,Fabricant
authorized_reseller,Authorized reseller,Revendeur autorisé
retailer,Retailer,Détaillant
marketplace_seller,Marketplace seller,Vendeur de place de marché
distributor,Distributor,Distributeur
refurbisher,Refurbisher,Reconditionneur
```

---

### shipping_availability.csv

```csv
id,en,fr
available,Available,Disponible
limited,Limited availability,Disponibilité limitée
local_only,Local delivery only,Livraison locale seulement
pickup_only,Pickup only,Cueillette seulement
unavailable,Unavailable,Indisponible
```

---

### standard_specs.csv

```csv
id,wifi_standard,bluetooth_version,ethernet_speed,usb_a_ports,usb_c_ports,hdmi_ports,battery_wh,power_adapter_w,chassis_material,camera_type,biometric_type,warranty_period
aspire_5_a515_58m,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
swift_go_14_sfg14_73,wifi_7,5.4,none,1,2,1,63,65,aluminum,1080p_ir,face_fingerprint,24_months
travelmate_p4_14_tmp414_53,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
predator_helios_16_ph16_72,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
nitro_v_15_anv15_51,wifi_6e,5.3,1_gbps,3,1,1,80,230,aluminum_plastic,1080p,none,12_months
mac_mini_m4,wifi_6e,5.3,2.5_gbps,3,2,2,,90,aluminum_plastic,none,none,12_months
imac_24_m4,wifi_6e,5.3,1_gbps,3,2,1,,135,aluminum_plastic,1080p_ir,face_recognition,12_months
mac_studio_m4_max,wifi_7,5.4,10_gbps,8,2,1,,1200,steel,none,none,36_months
mac_pro_m2_ultra,wifi_7,5.4,10_gbps,8,2,1,,1200,steel,none,none,36_months
expertbook_b5_b5404,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
proart_p16_h7606,wifi_7,5.4,2.5_gbps,2,2,1,95,230,aluminum,1080p_ir,face_fingerprint,36_months
envy_16_2024,wifi_7,5.4,none,1,2,1,63,65,aluminum,1080p_ir,face_fingerprint,24_months
victus_16_2024,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
thinkbook_14_gen7,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
loq_15_gen9,wifi_6e,5.3,1_gbps,3,1,1,80,230,aluminum_plastic,1080p,none,12_months
thinkstation_p3_tower_gen2,wifi_7,5.4,10_gbps,8,2,1,,1200,steel,none,none,36_months
surface_studio_2_plus_2022,wifi_7,5.4,2.5_gbps,4,2,1,,180,aluminum,1440p_ir,face_fingerprint,24_months
modern_14_c13m,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
prestige_14_ai_studio_c1v,wifi_7,5.4,none,1,2,1,63,65,aluminum,1080p_ir,face_fingerprint,24_months
stealth_16_ai_studio_a1v,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
raider_18_hx_a14v,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
vector_16_hx_a14v,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
creator_z16_hx_studio_2023,wifi_7,5.4,2.5_gbps,2,2,1,95,230,aluminum,1080p_ir,face_fingerprint,36_months
predator_orion_5000_2025,wifi_7,5.4,2.5_gbps,6,2,1,,850,steel_tempered_glass,none,none,24_months
precision_3680_tower_2024,wifi_7,5.4,10_gbps,8,2,1,,1200,steel,none,none,36_months
alienware_aurora_r16,wifi_7,5.4,2.5_gbps,6,2,1,,850,steel_tempered_glass,none,none,24_months
omen_35l_2024,wifi_7,5.4,2.5_gbps,6,2,1,,850,steel_tempered_glass,none,none,24_months
inspiron_24_aio_5430,wifi_6e,5.3,1_gbps,3,2,1,,135,aluminum_plastic,1080p_ir,face_recognition,12_months
pavilion_24_aio_2024,wifi_6e,5.3,1_gbps,3,2,1,,135,aluminum_plastic,1080p_ir,face_recognition,12_months
poweredge_r760_2023,wifi_none,none,25_gbps,6,1,0,,1600,steel,none,none,36_months
poweredge_t560_2023,wifi_none,none,10_gbps,6,1,0,,800,steel,none,none,36_months
proliant_dl380_gen11,wifi_none,none,25_gbps,6,1,0,,1600,steel,none,none,36_months
superserver_sys_221h_tnr_2023,wifi_none,none,25_gbps,6,1,0,,1600,steel,none,none,36_months
raspberry_pi_5_2023,wifi_5,5.0,1_gbps,4,1,2,,27,pcb,none,none,12_months
z2_tower_g9_2022,wifi_7,5.4,10_gbps,8,2,1,,1200,steel,none,none,36_months
thinkpad_p14s_gen5,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
ideapad_slim_5_gen9,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
yoga_7_gen9,wifi_7,5.4,none,1,2,1,68,65,aluminum,1080p_ir,face_fingerprint,24_months
xps_13_9345,wifi_6e,5.3,none,1,2,0,55,65,aluminum,1080p_ir,face_recognition,12_months
xps_16_9640,wifi_7,5.4,none,1,2,1,63,65,aluminum,1080p_ir,face_fingerprint,24_months
latitude_5450_2024,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
precision_5690_2024,wifi_7,5.4,2.5_gbps,2,2,1,95,230,aluminum,1080p_ir,face_fingerprint,36_months
inspiron_16_5640,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
alienware_m16_r2,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
elitebook_840_g11,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
probook_450_g11,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
zbook_firefly_14_g11,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
pavilion_15_2024,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
omen_16_2024,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
zenbook_14_ux3405,wifi_7,5.4,none,1,2,1,63,65,aluminum,1080p_ir,face_fingerprint,24_months
vivobook_16_x1605,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
rog_zephyrus_g14_ga403,wifi_7,5.4,2.5_gbps,3,2,1,99,330,aluminum,1080p_ir,face_recognition,24_months
tuf_gaming_a15_fa507,wifi_6e,5.3,1_gbps,3,1,1,80,230,aluminum_plastic,1080p,none,12_months
macbook_air_15_m4,wifi_6e,5.3,none,0,2,0,53,35,aluminum,1080p,biometric_fingerprint,12_months
surface_laptop_13_first_edition,wifi_6e,5.3,none,1,2,0,55,65,aluminum,1080p_ir,face_recognition,12_months
surface_pro_13_11th_edition,wifi_7,5.4,none,0,2,0,48,65,aluminum,1080p_ir,face_recognition,12_months
framework_laptop_13_2025,wifi_7,5.4,none,1,2,0,57,65,magnesium_alloy,1080p_ir,face_fingerprint,36_months
razer_blade_14_2025,wifi_7,5.4,2.5_gbps,3,2,1,99,330,aluminum,1080p_ir,face_recognition,24_months
galaxy_book5_pro_14_2025,wifi_7,5.4,none,1,2,1,63,65,aluminum,1080p_ir,face_fingerprint,24_months
thinkpad_t14_gen5,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
thinkpad_t14_gen6,wifi_7,5.4,1_gbps,2,2,1,57,65,magnesium_alloy,1080p_ir,face_fingerprint,36_months
thinkpad_x1_carbon_gen12,wifi_7,5.4,none,1,2,1,63,65,aluminum,1080p_ir,face_fingerprint,24_months
thinkpad_x1_carbon_gen13,wifi_7,5.4,none,1,2,1,63,65,aluminum,1080p_ir,face_fingerprint,24_months
legion_5_gen9,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
legion_5_gen10,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
macbook_air_m3,wifi_6e,5.3,none,0,2,0,53,35,aluminum,1080p,biometric_fingerprint,12_months
macbook_air_m4,wifi_6e,5.3,none,0,2,0,53,35,aluminum,1080p,biometric_fingerprint,12_months
macbook_pro_m4,wifi_6e,5.3,none,0,3,1,72,70,aluminum,1080p,biometric_fingerprint,12_months
macbook_pro_m4_pro,wifi_6e,5.3,none,0,3,1,72,70,aluminum,1080p,biometric_fingerprint,12_months
macbook_pro_m4_max,wifi_6e,5.3,none,0,3,1,100,140,aluminum,1080p,biometric_fingerprint,12_months
optiplex_7020_2024,wifi_6e,5.3,1_gbps,6,2,1,,260,steel_plastic,none,none,36_months
thinkcentre_m90s_gen5,wifi_6e,5.3,1_gbps,6,2,1,,260,steel_plastic,none,none,36_months
asus_nuc_14_pro_2024,wifi_7,5.4,2.5_gbps,4,2,2,,120,aluminum_plastic,none,none,36_months
zotac_zbox_magnus_en474070c,wifi_7,5.4,2.5_gbps,4,2,2,,330,aluminum,none,none,24_months
ultrabook_13_standard,wifi_6e,5.3,none,1,2,0,55,65,aluminum,1080p_ir,face_recognition,12_months
ultrabook_13_business,wifi_7,5.4,none,1,2,0,57,65,magnesium_alloy,1080p_ir,face_fingerprint,36_months
business_laptop_14_standard,wifi_6e,5.3,1_gbps,2,2,1,52,65,aluminum_plastic,1080p_ir,fingerprint,36_months
business_laptop_14_docked,wifi_7,5.4,1_gbps,2,2,1,57,65,magnesium_alloy,1080p_ir,face_fingerprint,36_months
business_laptop_14_cellular,wifi_7,5.4,1_gbps,2,2,1,57,65,magnesium_alloy,1080p_ir,face_fingerprint,36_months
premium_laptop_14,wifi_7,5.4,none,1,2,1,63,65,aluminum,1080p_ir,face_fingerprint,24_months
convertible_laptop_14,wifi_7,5.4,none,1,2,1,68,65,aluminum,1080p_ir,face_fingerprint,24_months
detachable_13,wifi_7,5.4,none,0,2,0,48,65,aluminum,1080p_ir,face_recognition,12_months
gaming_laptop_15,wifi_6e,5.3,1_gbps,3,1,1,80,230,aluminum_plastic,1080p,none,12_months
gaming_laptop_16,wifi_7,5.4,2.5_gbps,3,2,1,90,280,aluminum_plastic,1080p_ir,face_recognition,12_months
premium_gaming_laptop_16,wifi_7,5.4,2.5_gbps,3,2,1,99,330,aluminum,1080p_ir,face_recognition,24_months
mobile_workstation_16,wifi_7,5.4,2.5_gbps,2,2,1,95,230,aluminum,1080p_ir,face_fingerprint,36_months
macbook_air_13,wifi_6e,5.3,none,0,2,0,53,35,aluminum,1080p,biometric_fingerprint,12_months
macbook_pro_14,wifi_6e,5.3,none,0,3,1,72,70,aluminum,1080p,biometric_fingerprint,12_months
macbook_pro_16,wifi_6e,5.3,none,0,3,1,100,140,aluminum,1080p,biometric_fingerprint,12_months
desktop_tower_consumer,wifi_6,5.2,1_gbps,6,2,1,,300,steel_plastic,none,none,12_months
desktop_tower_gaming,wifi_7,5.4,2.5_gbps,6,2,1,,850,steel_tempered_glass,none,none,24_months
desktop_workstation_tower,wifi_7,5.4,10_gbps,8,2,1,,1200,steel,none,none,36_months
desktop_sff_business,wifi_6e,5.3,1_gbps,6,2,1,,260,steel_plastic,none,none,36_months
desktop_micro_business,wifi_6e,5.3,1_gbps,4,2,1,,135,plastic_metal,none,none,36_months
all_in_one_24,wifi_6e,5.3,1_gbps,3,2,1,,135,aluminum_plastic,1080p_ir,face_recognition,12_months
all_in_one_27,wifi_7,5.4,2.5_gbps,4,2,1,,180,aluminum,1440p_ir,face_fingerprint,24_months
mini_pc_standard,wifi_6e,5.3,2.5_gbps,3,2,2,,90,aluminum_plastic,none,none,12_months
mini_pc_business,wifi_7,5.4,2.5_gbps,4,2,2,,120,aluminum_plastic,none,none,36_months
mini_pc_performance,wifi_7,5.4,2.5_gbps,4,2,2,,330,aluminum,none,none,24_months
single_board_computer,wifi_5,5.0,1_gbps,4,1,2,,27,pcb,none,none,12_months
server_tower,wifi_none,none,10_gbps,6,1,0,,800,steel,none,none,36_months
server_rack_1u,wifi_none,none,10_gbps,4,1,0,,900,steel,none,none,36_months
server_rack_2u,wifi_none,none,25_gbps,6,1,0,,1600,steel,none,none,36_months
server_blade,wifi_none,none,25_gbps,2,0,0,,1800,steel,none,none,36_months
```

---

### storage.csv

```csv
id,en,fr,storage_type,capacity_gb
microsd_64gb,64 GB microSD,64 Go microSD,microsd,64
hdd_500gb,500 GB HDD,500 Go HDD,hdd,500
hdd_1tb,1 TB HDD,1 To HDD,hdd,1000
hdd_2tb,2 TB HDD,2 To HDD,hdd,2000
hdd_4tb,4 TB HDD,4 To HDD,hdd,4000
hdd_8tb,8 TB HDD,8 To HDD,hdd,8000
hdd_12tb,12 TB HDD,12 To HDD,hdd,12000
hdd_16tb,16 TB HDD,16 To HDD,hdd,16000
sata_ssd_128gb,128 GB SATA SSD,128 Go SSD SATA,sata_ssd,128
sata_ssd_256gb,256 GB SATA SSD,256 Go SSD SATA,sata_ssd,256
sata_ssd_500gb,500 GB SATA SSD,500 Go SSD SATA,sata_ssd,500
sata_ssd_512gb,512 GB SATA SSD,512 Go SSD SATA,sata_ssd,512
sata_ssd_1tb,1 TB SATA SSD,1 To SSD SATA,sata_ssd,1000
sata_ssd_2tb,2 TB SATA SSD,2 To SSD SATA,sata_ssd,2000
sata_ssd_4tb,4 TB SATA SSD,4 To SSD SATA,sata_ssd,4000
nvme_ssd_128gb,128 GB NVMe SSD,128 Go SSD NVMe,nvme_ssd,128
nvme_ssd_256gb,256 GB NVMe SSD,256 Go SSD NVMe,nvme_ssd,256
nvme_ssd_512gb,512 GB NVMe SSD,512 Go SSD NVMe,nvme_ssd,512
nvme_ssd_1tb,1 TB NVMe SSD,1 To SSD NVMe,nvme_ssd,1000
nvme_ssd_2tb,2 TB NVMe SSD,2 To SSD NVMe,nvme_ssd,2000
nvme_ssd_4tb,4 TB NVMe SSD,4 To SSD NVMe,nvme_ssd,4000
nvme_ssd_8tb,8 TB NVMe SSD,8 To SSD NVMe,nvme_ssd,8000
pcie_ssd_512gb,512 GB PCIe SSD,512 Go SSD PCIe,pcie_ssd,512
pcie_ssd_1tb,1 TB PCIe SSD,1 To SSD PCIe,pcie_ssd,1000
pcie_ssd_2tb,2 TB PCIe SSD,2 To SSD PCIe,pcie_ssd,2000
pcie_ssd_4tb,4 TB PCIe SSD,4 To SSD PCIe,pcie_ssd,4000
pcie_ssd_8tb,8 TB PCIe SSD,8 To SSD PCIe,pcie_ssd,8000
emmc_64gb,64 GB eMMC,64 Go eMMC,emmc,64
emmc_128gb,128 GB eMMC,128 Go eMMC,emmc,128
emmc_256gb,256 GB eMMC,256 Go eMMC,emmc,256
ufs_128gb,128 GB UFS,128 Go UFS,ufs,128
ufs_256gb,256 GB UFS,256 Go UFS,ufs,256
ufs_512gb,512 GB UFS,512 Go UFS,ufs,512
ufs_1tb,1 TB UFS,1 To UFS,ufs,1000
```

---

### warehouse.csv

```csv
id,en,fr,market
ca_east,Canada East,Canada Est,ca
ca_central,Canada Central,Canada Centre,ca
ca_west,Canada West,Canada Ouest,ca
us_east,United States East,États-Unis Est,us
us_central,United States Central,États-Unis Centre,us
us_west,United States West,États-Unis Ouest,us
eu_west,Europe West,Europe Ouest,eu
eu_central,Europe Central,Europe Centre,eu
```

---
