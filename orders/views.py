import datetime

from django.contrib.sites.shortcuts import get_current_site
from django.shortcuts import render, redirect
from django.http import JsonResponse

from carts.models import CartItem
from store.models import Product
from .forms import OrderForm
from .models import Order, Payment, OrderProduct
import json
from django.core.mail import EmailMessage
from django.template.loader import render_to_string


def payments(request):
    body = json.loads(request.body)
    order = Order.objects.get(user=request.user, is_ordered=False, order_number=body['orderID'])

    # Storing transaction details in Payment model
    payment = Payment(
        user=request.user,
        payment_id=body['transID'],
        payment_method=body['payment_method'],
        amount_paid=order.order_total,
        status=body['status'],
    )
    payment.save()

    order.payment = payment
    order.is_ordered = True
    order.save()

    # Save cart items in Order Product table
    cart_items = CartItem.objects.filter(user=request.user)
    for item in cart_items:
        order_product = OrderProduct()
        order_product.order_id = order.id
        order_product.payment = payment
        order_product.user_id = request.user.id
        order_product.product_id = item.product_id
        order_product.quantity = item.quantity
        order_product.product_price = item.product.price
        order_product.ordered = True
        order_product.save()

        cart_item = CartItem.objects.get(id=item.id)
        product_variation = cart_item.variations.all()
        order_product = OrderProduct.objects.get(id=order_product.id)
        order_product.variations.set(product_variation)
        order_product.save()

        # Reducing the quantity of the sold product
        product = Product.objects.get(id=item.product_id)
        product.stock -= item.quantity
        product.save()

    # Clearing cart
    CartItem.objects.filter(user=request.user).delete()

    # Sending order received email to customer
    current_site = get_current_site(request)
    mail_subject = 'Thank you for your order'
    message = render_to_string('orders/order_received_email.html', {
        'user': request.user,
        'order': order,
        'domain': current_site,
    })
    to_email = request.user.email
    send_email = EmailMessage(mail_subject, message, to=[to_email])
    send_email.send()

    # Sending data back to js sendData method
    data = {
        'order_number': order.order_number,
        'transacID': payment.payment_id,
    }

    return JsonResponse(data)


def generate_order_number(data):
    yr = int(datetime.date.today().strftime('%Y'))
    dt = int(datetime.date.today().strftime('%d'))
    mt = int(datetime.date.today().strftime('%m'))
    d = datetime.date(yr, mt, dt)
    current_date = d.strftime("%Y%m%d")
    order_number = current_date + str(data.id)
    return order_number


def place_order(request):
    current_user = request.user
    cart_items = CartItem.objects.filter(user=current_user)
    cart_count = cart_items.count()
    if cart_count <= 0:
        return redirect('store')

    total = 0
    for cart_item in cart_items:
        total += (cart_item.product.price * cart_item.quantity)

    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            data = Order()
            data.user = current_user
            data.first_name = form.cleaned_data['first_name']
            data.last_name = form.cleaned_data['last_name']
            data.phone = form.cleaned_data['phone']
            data.email = form.cleaned_data['email']
            data.address_line_1 = form.cleaned_data['address_line_1']
            data.address_line_2 = form.cleaned_data['address_line_2']
            data.country = form.cleaned_data['country']
            data.state = form.cleaned_data['state']
            data.city = form.cleaned_data['city']
            data.order_note = form.cleaned_data['order_note']
            data.order_total = total
            data.ip = request.META.get('REMOTE_ADDR')
            data.save()
            order_number = generate_order_number(data)
            data.order_number = order_number
            data.save()

            order = Order.objects.get(user=current_user, is_ordered=False, order_number=order_number)
            context = {
                'order': order,
                'cart_items': cart_items,
                'total': total,
            }
            return render(request, 'orders/payments.html', context)
    else:
        return redirect('checkout')


def order_complete(request):
    order_number = request.GET.get('order_number')
    transaction_id = request.GET.get('payment_id')

    try:
        order = Order.objects.get(order_number=order_number, is_ordered=True)
        ordered_products = OrderProduct.objects.filter(order_id=order.id)

        total = 0
        for i in ordered_products:
            total += i.product_price * i.quantity

        payment = Payment.objects.get(payment_id=transaction_id)

        context = {
            'order': order,
            'ordered_products': ordered_products,
            'order_number': order.order_number,
            'trans_id': payment.payment_id,
            'payment': payment,
            'total': total,
        }
        return render(request, 'orders/order_complete.html', context)
    except (Payment.DoesNotExist, Order.DoesNotExist):
        return redirect('home')
