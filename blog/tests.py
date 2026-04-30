from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from blog.models import Category, Post


class PostDetailSanitizationTests(TestCase):
    def setUp(self):
        author = User.objects.create_user(username="writer", password="secret123")
        category = Category.objects.create(name="Travel")
        self.post = Post.objects.create(
            author=author,
            title="Safe travel guide",
            image=SimpleUploadedFile("post.jpg", b"post-image", content_type="image/jpeg"),
            description=(
                "<p>Welcome <strong>travellers</strong>.</p>"
                "<script>xss-blog-script</script>"
                '<a href="javascript:alert(\'xss-blog-link\')">bad link</a>'
            ),
            category=category,
        )

    def test_post_detail_sanitizes_stored_html_before_rendering(self):
        response = self.client.get(reverse("blog:post_detail", args=[self.post.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<strong>travellers</strong>", html=False)
        self.assertNotContains(response, "xss-blog-script")
        self.assertNotContains(response, "javascript:alert")
