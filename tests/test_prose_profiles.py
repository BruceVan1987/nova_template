import unittest
from unittest import mock
from test_story_scaffold import load_story_module

class ProseProfileTests(unittest.TestCase):
    def setUp(self):
        self.story=load_story_module()

    def test_new_project_does_not_enforce_colloquial_register(self):
        body="---\n\n明早他便动身，余下三日再说。"
        categories=[item[1] for item in self.story.find_prose_style_warnings(body)]
        self.assertNotIn("轻度书面词密度",categories)
        self.assertIsNone(self.story._light_register_gate_error({"fm":{"chapter":1}},body))

    def test_project_can_select_its_own_pattern_and_warning_threshold(self):
        config={"light_register":{"enabled":True,"pattern":"忽然","warn_per_k":1}}
        with mock.patch.object(self.story,"LINT_CONFIG",config):
            warnings=self.story.find_prose_style_warnings("---\n\n他忽然开了门。")
            self.assertIn("轻度书面词密度",[item[1] for item in warnings])
            warnings=self.story.find_prose_style_warnings("---\n\n明早他便动身。")
            self.assertNotIn("轻度书面词密度",[item[1] for item in warnings])

    def test_confirmed_prose_is_not_retroactively_warned(self):
        config={"light_register":{"enabled":True,"warn_per_k":1},"bare_dialogue":{"enabled":True}}
        with mock.patch.object(self.story,"LINT_CONFIG",config):
            categories=[item[1] for item in self.story.find_prose_style_warnings("---\n\n明早他便动身。",status="已确认")]
            self.assertNotIn("轻度书面词密度",categories)

    def test_dialogue_warning_is_optional_and_does_not_trigger_on_three_paragraphs(self):
        four="---\n\n“甲。”\n\n“乙。”\n\n“丙。”\n\n“丁。”"
        self.assertNotIn("纯对白串",[item[1] for item in self.story.find_prose_style_warnings(four)])
        with mock.patch.object(self.story,"LINT_CONFIG",{"bare_dialogue":{"enabled":True}}):
            self.assertIn("纯对白串",[item[1] for item in self.story.find_prose_style_warnings(four)])
            self.assertNotIn("纯对白串",[item[1] for item in self.story.find_prose_style_warnings(four.rsplit("\n\n",1)[0])])

    def test_title_does_not_count_toward_register_gate(self):
        with mock.patch.object(self.story,"LINT_CONFIG",{"light_register":{"enabled":True,"pattern":"明早","block_per_k":1}}):
            chapter={"fm":{"chapter":1}}
            self.assertIsNone(self.story._light_register_gate_error(chapter,"# 第1章 明早\n\n他推开门。"))

class ProseProfileConfigTests(unittest.TestCase):
    def test_invalid_profiles_are_reported_without_crashing(self):
        import importlib.util, json, tempfile
        from pathlib import Path
        from test_story_scaffold import ROOT
        spec=importlib.util.spec_from_file_location("doctor_profile",ROOT/"scripts/doctor.py")
        doctor=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(doctor)
        base=json.loads((ROOT/"novel-project.json").read_text())
        with tempfile.TemporaryDirectory() as td:
            config=Path(td)/"config.json"
            with mock.patch.object(doctor,"CONFIG_PATH",config):
                for profile in [{"enabled":"false"},{"warn_per_k":0},{"block_per_k":float("inf")},{"pattern":"["},{"pattern":"x*"},{"pattern":""}]:
                    with self.subTest(profile=profile):
                        base["lint"]["light_register"]=profile
                        config.write_text(json.dumps(base))
                        self.assertTrue(doctor.project_config_problems())
                base["lint"]["light_register"]={"enabled":True,"pattern":"忽然","warn_per_k":1,"block_per_k":2}
                config.write_text(json.dumps(base))
                self.assertEqual(doctor.project_config_problems(),[])
