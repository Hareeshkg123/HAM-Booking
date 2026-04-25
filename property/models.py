from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
import builtins


# Create your models here.

class Property(models.Model):
    owner = models.ForeignKey(User, related_name='property_owner', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    image = models.ImageField(upload_to='Property/')
    price = models.IntegerField(default=0)
    description = models.TextField(max_length=10000) 
    places = models.ForeignKey('Place', related_name='property_place', on_delete=models.CASCADE)
    category = models.ForeignKey('Category', related_name='property_category', on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)
    slug = models.SlugField(null=True , blank=True)
    
    def save(self, *args, **kwargs):
       if not self.slug:
           self.slug = slugify(self.name)
       super(Property, self).save(*args, **kwargs) # Call the real save() method
    
    def __str__(self):
        return self.name
       
       
    def get_absolute_url(self):
        return reverse("property:property_detail", kwargs={"slug": self.slug})
       
 
class PropertyImages(models.Model):
    property = models.ForeignKey(Property, related_name='property_image', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='propertyimages/')
    def __str__(self):
        return str(self.property)
    

 
    
        

class Place(models.Model):
    name = models.CharField(max_length=50)
    image = models.ImageField(upload_to='places/')
    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=40)
    icon = models.CharField(max_length=30)
    
    def __str__(self):
        return self.name
        
        

class PropertyReview(models.Model):
    author = models.ForeignKey(User, related_name='review_author', on_delete=models.CASCADE)
    property = models.ForeignKey(Property, related_name='review_property', on_delete=models.CASCADE)
    rate = models.IntegerField(default=0)
    feedback = models.TextField(max_length=2000)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return str(self.property)
    


COUNT = (
    (1,'1'),
    (2,'2'),
    (3,'3'),
    (4,'4'),
    (5,'5'),
)

CHILD_COUNT = (
    (0, '0'),
    (1, '1'),
    (2, '2'),
    (3, '3'),
    (4, '4'),
    (5, '5'),
)
    
    
class PropertyBook(models.Model):
    user = models.ForeignKey(User, related_name='book_owner', on_delete=models.CASCADE)
    property = models.ForeignKey(Property, related_name='book_property', on_delete=models.CASCADE)
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True)
    date_from = models.DateField(default=timezone.now)
    date_to = models.DateField(default=timezone.now)
    guest = models.IntegerField( choices= COUNT)
    children =  models.IntegerField( choices= CHILD_COUNT)
    STATUS_CHOICES = (
        ('pending', 'Booked'),
        ('confirmed', 'Booked'),
        ('cancelled', 'Cancelled'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    def __str__(self):
        return str(self.property)
    
    @builtins.property
    def nights(self):
        """Return number of nights for the booking (at least 1)."""
        try:
            delta = self.date_to - self.date_from
            return max(1, delta.days)
        except Exception:
            return 1

    @builtins.property
    def total_cost(self):
        """Return total cost (price per night * nights)."""
        try:
            return int(self.property.price) * self.nights
        except Exception:
            return 0
            
