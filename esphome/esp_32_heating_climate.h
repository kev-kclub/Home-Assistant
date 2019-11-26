#include "esphome.h"

using namespace esphome::climate;

class kclubClimate : public Component, public Climate {
 public:
  
  kclubClimate(esphome::dallas::DallasTemperatureSensor **tempsensor, 
    esphome::gpio::GPIOSwitch **gpiorelay, 
    esphome::homeassistant::HomeassistantSensor **overridetemp, 
    esphome::homeassistant::HomeassistantSensor **awaytemp) {
    this->tempsensor_ = tempsensor;
    this->gpiorelay_ = gpiorelay;
    this->overridetemp_ = overridetemp;
    this->awaytemp_ = awaytemp;
  }

  void setup() override {
    // This will be called by App.setup()
    this->target_temperature = 15.0;
    this->mode = esphome::climate::ClimateMode::CLIMATE_MODE_AUTO;
    this->action = climate::CLIMATE_ACTION_OFF;
    this->current_temperature = 0.0;
    
    if (*this->tempsensor_ != nullptr) {
      (*this->tempsensor_)->add_on_state_callback([this](float state) {
        ESP_LOGI("custom", "Climate receive temperature update: %f", state);
        this->current_temperature = state;
        this->turnonoff();
        this->publish_state();
      });
    }
    if (*this->overridetemp_ != nullptr) {
      (*this->overridetemp_)->add_on_state_callback([this](float state) {
        ESP_LOGI("custom", "Climate receive override temperature update: %f", state);
        if (mode == CLIMATE_MODE_HEAT) {
          this->target_temperature = state;
          this->turnonoff();
          this->publish_state();
        }
      });
    }
    if (*this->awaytemp_ != nullptr) {
      (*this->awaytemp_)->add_on_state_callback([this](float state) {
        ESP_LOGI("custom", "Climate receive away temperature update: %f", state);
        if (mode == CLIMATE_MODE_OFF) {
          this->target_temperature = state;
          this->turnonoff();
          this->publish_state();
        }
      });
    }
  }
  
  void control(const ClimateCall &call) override {
    if (call.get_mode().has_value()) {
      // User requested mode change (auto, heat, off)
      ClimateMode mode = *call.get_mode();
      // Publish updated state
      this->mode = mode;
      if (mode == CLIMATE_MODE_OFF) {
        this->target_temperature = (*this->awaytemp_)->state;
      }
      if (mode == CLIMATE_MODE_HEAT) {
        this->target_temperature = (*this->overridetemp_)->state;
      }
    }
    if (call.get_target_temperature().has_value()) {
      // User requested target temperature change
      float temp = *call.get_target_temperature();
      this->target_temperature = temp;
    }
    this->turnonoff();
    this->publish_state();
  }
  
  void turnonoff() {
    // use this to determine if heating should be turned on or off and set gpio switch output
    if (this->target_temperature - this->current_temperature > 0.1) {
      (*this->gpiorelay_)->turn_on();
      this->action = climate::CLIMATE_ACTION_HEATING;
    }
    else if (this->current_temperature - this->target_temperature > 0.1){
      (*this->gpiorelay_)->turn_off();
      this->action = climate::CLIMATE_ACTION_OFF;
    }
  }

  climate::ClimateTraits traits() override {
    auto traits = climate::ClimateTraits();
    traits.set_supports_current_temperature(true);
    traits.set_supports_auto_mode(true);
    traits.set_supports_cool_mode(false);
    traits.set_supports_heat_mode(true);
    traits.set_supports_two_point_target_temperature(false);
    traits.set_supports_away(false);
    traits.set_supports_action(true);
    return traits;
  }
  
 protected:
  esphome::dallas::DallasTemperatureSensor **tempsensor_{nullptr};
  esphome::gpio::GPIOSwitch **gpiorelay_{nullptr};
  esphome::homeassistant::HomeassistantSensor **awaytemp_{nullptr};
  esphome::homeassistant::HomeassistantSensor **overridetemp_{nullptr};
};
