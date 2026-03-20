#include "CorridorKeyPlugin.h"
#include "ofxsImageEffect.h"

namespace corridorkey {

// Plugin factory instance
static CorridorKeyPluginFactory gPluginFactory;

} // namespace corridorkey

// OFX entry point: register our plugin with the OFX support library
namespace OFX {
namespace Plugin {

void getPluginIDs(OFX::PluginFactoryArray& ids)
{
    ids.push_back(&corridorkey::gPluginFactory);
}

} // namespace Plugin
} // namespace OFX
