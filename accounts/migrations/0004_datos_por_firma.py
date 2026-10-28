from django.db import migrations, models


def copy_profile_data(apps, schema_editor):
    """Cada firma existente toma los datos de su perfil."""
    SignatureImage = apps.get_model("accounts", "SignatureImage")
    for img in SignatureImage.objects.select_related("profile"):
        img.full_name = img.profile.full_name
        img.id_document = img.profile.id_document
        img.email = img.profile.email
        img.title = img.profile.title
        img.save(update_fields=["full_name", "id_document", "email", "title"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_signatureimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="signatureimage",
            name="full_name",
            field=models.CharField(default="", max_length=150, verbose_name="nombre completo"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="signatureimage",
            name="id_document",
            field=models.CharField(default="", max_length=30, verbose_name="documento de identidad"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="signatureimage",
            name="email",
            field=models.EmailField(default="", max_length=254, verbose_name="correo de firma"),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="signatureimage",
            name="title",
            field=models.CharField(blank=True, max_length=150, verbose_name="cargo"),
        ),
        migrations.AlterField(
            model_name="signatureimage",
            name="name",
            field=models.CharField(default="Firma principal", max_length=80, verbose_name="nombre de la firma"),
        ),
        migrations.RunPython(copy_profile_data, migrations.RunPython.noop),
    ]
