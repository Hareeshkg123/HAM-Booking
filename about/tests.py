from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from about.models import About, FAQ


class AboutPageSanitizationTests(TestCase):
    def setUp(self):
        About.objects.create(
            what_we_do="<p>We host <strong>great stays</strong>.</p><script>xss-about-what</script>",
            our_mission='<p>Mission text</p><iframe src="https://evil.example/xss-about-mission"></iframe>',
            our_goals='<p>Goals text</p><a href="javascript:alert(\'xss-about-goal\')">bad</a>',
            image=SimpleUploadedFile("about.jpg", b"about-image", content_type="image/jpeg"),
        )
        FAQ.objects.create(title="Is it safe?", description="Yes.")

    def test_about_page_sanitizes_tab_content(self):
        response = self.client.get(reverse("about:about"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<strong>great stays</strong>", html=False)
        self.assertNotContains(response, "xss-about-what")
        self.assertNotContains(response, "xss-about-mission")
        self.assertNotContains(response, "javascript:alert")
