from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from orders.models import Order, Driver, Vehicle, OrderMessage


class Command(BaseCommand):
    help = 'Seeds the database with sample data for frontend developers.'

    @transaction.atomic
    def handle(self, *args, **kwargs):
        self.stdout.write("Starting database seeding...")

        # 1. Create Core Users
        password = "Password123!"

        admin, _ = User.objects.get_or_create(email="admin@agrotrack.com", defaults={
            "full_name": "System Admin",
            "role": User.Role.ADMIN,
            "is_verified": True,
            "is_active": True,
            "is_staff": True,
            "is_superuser": True,
        })
        if not admin.check_password(password):
            admin.set_password(password)
            admin.save()

        dispatcher, _ = User.objects.get_or_create(email="dispatcher@agrotrack.com", defaults={
            "full_name": "Lade Akomolafe",
            "role": User.Role.DISPATCHER,
            "is_verified": True,
            "is_active": True,
        })
        if not dispatcher.check_password(password):
            dispatcher.set_password(password)
            dispatcher.save()

        sender, _ = User.objects.get_or_create(email="sender@agrotrack.com", defaults={
            "full_name": "Ephraim Okon",
            "role": User.Role.SENDER,
            "is_verified": True,
            "is_active": True,
        })
        if not sender.check_password(password):
            sender.set_password(password)
            sender.save()

        self.stdout.write(self.style.SUCCESS(f"Created core users (Password: {password})"))

        # 2. Create Drivers
        drivers_data = [
            {"name": "Chinedu Okafor", "phone": "08012345678"},
            {"name": "Babajide Sanwo", "phone": "08123456789"},
            {"name": "Emeka Ike", "phone": "09012345670"},
            {"name": "Ibrahim Musa", "phone": "07012345671"},
        ]
        drivers = []
        for d in drivers_data:
            driver, _ = Driver.objects.get_or_create(name=d["name"], defaults={"phone": d["phone"]})
            drivers.append(driver)

        # 3. Create Vehicles
        vehicles_data = [
            {"registration_number": "LAG-123-AB", "vehicle_type": "Truck", "capacity_tonnes": 5.00},
            {"registration_number": "ABJ-456-XY", "vehicle_type": "Truck", "capacity_tonnes": 10.00},
            {"registration_number": "KNO-789-QW", "vehicle_type": "Van", "capacity_tonnes": 1.50},
            {"registration_number": "PHC-321-ZA", "vehicle_type": "Motorcycle", "capacity_tonnes": 0.10},
        ]
        vehicles = []
        for v in vehicles_data:
            vehicle, _ = Vehicle.objects.get_or_create(
                registration_number=v["registration_number"],
                defaults={
                    "vehicle_type": v["vehicle_type"],
                    "capacity_tonnes": v["capacity_tonnes"],
                    "status": Vehicle.Status.AVAILABLE
                }
            )
            vehicles.append(vehicle)

        self.stdout.write(self.style.SUCCESS("Created drivers and vehicles"))

        # 4. Create Orders
        if Order.objects.count() > 0:
            self.stdout.write(self.style.WARNING("Orders already exist. Skipping order generation to avoid duplicates."))
            return

        now = timezone.now()

        # Order 1: New Request (Unassigned)
        Order.objects.create(
            sender=sender,
            pickup_address="14 Awolowo Road, Ikoyi, Lagos",
            pickup_contact_name="Mr. James",
            pickup_phone="08011111111",
            delivery_address="Shop 12, Alaba International Market, Lagos",
            delivery_name="Alaba Electronics",
            delivery_phone="08022222222",
            cargo_type="Electronics",
            cargo_weight=150.00,
            cargo_value=1500000.00,
            total_cost=25000.00,
            status=Order.Status.NEW_REQUEST,
            cargo_priority=Order.Priority.EXPRESS,
            pickup_date=now.date(),
            estimated_delivery_date=(now + timedelta(days=1)).date(),
        )

        # Order 2: Assigned
        Order.objects.create(
            sender=sender,
            dispatcher=dispatcher,
            driver=drivers[0],
            vehicle=vehicles[0],
            pickup_address="Farm 4, Ota, Ogun State",
            pickup_contact_name="Farmer Joe",
            pickup_phone="08033333333",
            delivery_address="Mile 12 Market, Lagos",
            delivery_name="Mama Tomato",
            delivery_phone="08044444444",
            cargo_type="Fresh Tomatoes",
            cargo_weight=500.00,
            cargo_value=200000.00,
            total_cost=45000.00,
            status=Order.Status.ASSIGNED,
            cargo_priority=Order.Priority.EXPRESS,
            pickup_date=now.date(),
            estimated_delivery_date=now.date(),
        )

        # Order 3: In Transit (with Chat History)
        order_in_transit = Order.objects.create(
            sender=sender,
            dispatcher=dispatcher,
            driver=drivers[1],
            vehicle=vehicles[1],
            pickup_address="Kano Rice Mills, Kano State",
            pickup_contact_name="Alhaji Kano",
            pickup_phone="08055555555",
            delivery_address="Trade Fair Complex, Lagos",
            delivery_name="Trade Fair Distributors",
            delivery_phone="08066666666",
            cargo_type="Bags of Rice",
            cargo_weight=8000.00,
            cargo_value=5000000.00,
            total_cost=350000.00,
            status=Order.Status.IN_TRANSIT,
            cargo_priority=Order.Priority.STANDARD,
            pickup_date=(now - timedelta(days=2)).date(),
            estimated_delivery_date=(now + timedelta(days=1)).date(),
            current_location="Currently passing through Lokoja, Kogi State"
        )

        # Order 3: Chat History
        OrderMessage.objects.create(
            order=order_in_transit,
            sender=sender,
            content="Hello, has the truck left Kano?",
            is_read=True
        )
        OrderMessage.objects.create(
            order=order_in_transit,
            sender=dispatcher,
            content="Yes, the driver left yesterday evening. Currently approaching Lokoja.",
            is_read=True
        )
        OrderMessage.objects.create(
            order=order_in_transit,
            sender=sender,
            content="Thanks! Any expected delays due to weather?",
            is_read=False
        )

        # Order 4: Delivered
        Order.objects.create(
            sender=sender,
            dispatcher=dispatcher,
            driver=drivers[2],
            vehicle=vehicles[2],
            pickup_address="Aba Market, Abia State",
            pickup_contact_name="Aba Textiles",
            pickup_phone="08077777777",
            delivery_address="Onitsha Main Market, Anambra State",
            delivery_name="Onitsha Traders",
            delivery_phone="08088888888",
            cargo_type="Textiles",
            cargo_weight=1200.00,
            cargo_value=800000.00,
            total_cost=60000.00,
            status=Order.Status.DELIVERED,
            cargo_priority=Order.Priority.STANDARD,
            pickup_date=(now - timedelta(days=1)).date(),
            estimated_delivery_date=now.date(),
        )

        # Order 5: Completed
        Order.objects.create(
            sender=sender,
            dispatcher=dispatcher,
            driver=drivers[3],
            vehicle=vehicles[3],
            pickup_address="Sokoto Farm, Sokoto State",
            pickup_contact_name="Sokoto Onions",
            pickup_phone="08099999999",
            delivery_address="Ibadan City Center, Oyo State",
            delivery_name="Ibadan Market",
            delivery_phone="08100000000",
            cargo_type="Onions",
            cargo_weight=3000.00,
            cargo_value=450000.00,
            total_cost=120000.00,
            status=Order.Status.COMPLETED,
            cargo_priority=Order.Priority.STANDARD,
            pickup_date=(now - timedelta(days=5)).date(),
            estimated_delivery_date=(now - timedelta(days=2)).date(),
        )

        self.stdout.write(self.style.SUCCESS("Successfully seeded Orders and Chat Messages."))
        self.stdout.write(self.style.SUCCESS("---"))
        self.stdout.write(self.style.SUCCESS("Database is fully seeded and ready for the frontend team!"))
        self.stdout.write(self.style.SUCCESS("Login credentials (all use password: Password123!):"))
        self.stdout.write(self.style.SUCCESS("  - admin@agrotrack.com"))
        self.stdout.write(self.style.SUCCESS("  - dispatcher@agrotrack.com"))
        self.stdout.write(self.style.SUCCESS("  - sender@agrotrack.com"))
