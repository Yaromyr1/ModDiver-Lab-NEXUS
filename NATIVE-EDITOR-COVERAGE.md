# Native Editor coverage — shared General / Nexus mapping update

Audited against the installed game. No installed inputs were modified.
General and staged Nexus reports match exactly. All 54 readable files retain byte-identical unchanged exports.

- 116,542 records.
- 46,806 resolved names or exact resource associations (previously 41,507).
- 69,344 additional mapped records, including 37,146 empty entity/index/hash slots.
- 392 records still lack a supported name or mapping.

Mappings preserve resource-to-record links even when only a resource ID is known. Enum mappings show the declared schema type and numeric value; collection containers and empty slots are identified separately. Network records require a matching entity slot and object ID. A mapping is not a recovered gameplay name. Unknown field meanings remain read-only.
Schema field-label coverage: 1,150 / 7,349.

Nexus loads the same 170 weapon display names from `native_names.json`, without requiring the external editor bundle.

Type library SHA-256: `4d4db6e7a057b9e5ad023894f1629f031520823be80ea6099cde8f3e27c0bee1`.

| File | Records | Named / associated | Mapped | Unresolved |
| --- | ---: | ---: | ---: | ---: |
| generated_add_resource_dependencies.dl_bin | 8 | 0 | 2 | 6 |
| generated_animation_event_trigger_settings.dl_bin | 214 | 179 | 35 | 0 |
| generated_arc_settings.dl_bin | 17 | 11 | 6 | 0 |
| generated_beam_settings.dl_bin | 31 | 22 | 9 | 0 |
| generated_body_settings.dl_bin | 2 | 2 | 0 | 0 |
| generated_candidate_descs.dl_bin | 13 | 0 | 1 | 12 |
| generated_collision_event_settings.dl_bin | 181 | 138 | 1 | 42 |
| generated_corporation_logos.dl_bin | 9 | 0 | 9 | 0 |
| generated_credits_settings.dl_bin | 4,516 | 2,331 | 2,185 | 0 |
| generated_customization_armor_sets.dl_bin | 422 | 111 | 311 | 0 |
| generated_customization_passive_bonuses.dl_bin | 33 | 32 | 1 | 0 |
| generated_damage_settings.dl_bin | 663 | 1 | 662 | 0 |
| generated_destruction_settings.dl_bin | 9,850 | 2,329 | 7,521 | 0 |
| generated_distant_war_effect_settings.dl_bin | 7 | 0 | 7 | 0 |
| generated_entities.dl_bin | 83,448 | 38,534 | 44,890 | 24 |
| generated_entity_deltas.dl_bin | 1 | 0 | 0 | 1 |
| generated_environment_settings.dl_bin | 17 | 17 | 0 | 0 |
| generated_explosion_settings.dl_bin | 425 | 5 | 420 | 0 |
| generated_font_lookup.dl_bin | 19 | 1 | 6 | 12 |
| generated_font_settings.dl_bin | 6 | 6 | 0 | 0 |
| generated_galactic_presence_settings.dl_bin | 137 | 131 | 6 | 0 |
| generated_generation_settings.dl_bin | 1 | 0 | 0 | 1 |
| generated_hit_effect_settings.dl_bin | 1,513 | 1,008 | 505 | 0 |
| generated_language_settings.dl_bin | 16 | 15 | 1 | 0 |
| generated_layer_package_indirection_settings.dl_bin | 9 | 0 | 1 | 8 |
| generated_location_groups.dl_bin | 13 | 0 | 0 | 13 |
| generated_modifier_settings.dl_bin | 15 | 0 | 0 | 15 |
| generated_planet_color_set_settings.dl_bin | 31 | 0 | 1 | 30 |
| generated_planet_data.dl_bin | 438 | 438 | 0 | 0 |
| generated_planet_override_settings.dl_bin | 57 | 44 | 13 | 0 |
| generated_planet_region_settings.dl_bin | 369 | 24 | 345 | 0 |
| generated_planet_territory_graphs.dl_bin | 11 | 0 | 0 | 11 |
| generated_planet_types_settings.dl_bin | 89 | 1 | 88 | 0 |
| generated_policy_settings.dl_bin | 24 | 0 | 22 | 2 |
| generated_projectile_settings.dl_bin | 356 | 355 | 1 | 0 |
| generated_region_settings.dl_bin | 87 | 13 | 74 | 0 |
| generated_resource_swap.dl_bin | — | — | — | Decoded file has no supported LDLD blocks. |
| generated_route_settings.dl_bin | 3 | 0 | 0 | 3 |
| generated_satellite_groups.dl_bin | 203 | 0 | 203 | 0 |
| generated_scenario_settings.dl_bin | 39 | 9 | 0 | 30 |
| generated_sky_settings.dl_bin | 80 | 0 | 40 | 40 |
| generated_solar_system_settings.dl_bin | 48 | 47 | 1 | 0 |
| generated_stamp_settings.dl_bin | 4,097 | 1 | 4,096 | 0 |
| generated_status_effect_settings.dl_bin | 104 | 92 | 12 | 0 |
| generated_stratagem_settings.dl_bin | 165 | 153 | 12 | 0 |
| generated_stratagem_upgrade_settings.dl_bin | 2 | 1 | 1 | 0 |
| generated_surface_effect_settings.dl_bin | 7,645 | 0 | 7,645 | 0 |
| generated_unit_customization_settings.dl_bin | 12 | 5 | 7 | 0 |
| generated_unit_effect_settings.dl_bin | 409 | 237 | 172 | 0 |
| generated_video_flow_settings.dl_bin | 11 | 0 | 1 | 10 |
| generated_video_ui_settings.dl_bin | 10 | 0 | 10 | 0 |
| generated_weapon_customization_settings.dl_bin | 261 | 252 | 9 | 0 |
| generated_weather_color_set_settings.dl_bin | 133 | 0 | 1 | 132 |
| generated_weather_settings.dl_bin | 184 | 184 | 0 | 0 |
| generated_zone_data.dl_bin | 88 | 77 | 11 | 0 |

Resource-swap blocks and nested entity-delta arrays retain the existing unsupported-layout limitations. File integrity and mapping parity were checked on Windows; this is not an in-game or Linux runtime test.

Run `source/audit_native_editor.py --game-data <data/game> --output <outside-game/report.json>` to reproduce the report.
